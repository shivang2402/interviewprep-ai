from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.email import EmailOperator
from airflow.models import Variable
from datetime import datetime, timedelta
import logging
import sys

sys.path.insert(0, '/home/shiv/airflow/dags')

from src.chunking.pipeline import run as run_chunking_pipeline
from src.embeddings.pipeline import run as run_embeddings_pipeline
from src.chunking import pipeline as chunking_pipeline_mod
from src.embeddings import pipeline as embeddings_pipeline_mod

logger = logging.getLogger("interviewprep.chunking_embedding_dag")

NOTIFY_EMAILS = [
    'kansara.dh@northeastern.edu',
    'lnu.prat@northeastern.edu',
    'patel.shivangm@northeastern.edu',
    'kanani.h@northeastern.edu',
    'shah.shreyc@northeastern.edu',
    'parikh.malh@northeastern.edu',
]


def _safe_variable_get(key, default):
    try:
        return Variable.get(key, default_var=default)
    except Exception:
        return default


def _as_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def chunking_task(**kwargs):
    """Run the chunking pipeline with optional demo limits."""
    dag_run = kwargs.get("dag_run")
    run_conf = dag_run.conf if dag_run and isinstance(dag_run.conf, dict) else {}

    demo_mode = _as_bool(run_conf.get(
        "demo_mode", _safe_variable_get("demo_mode", "false")
    ))
    demo_limit = _as_int(run_conf.get(
        "demo_limit_chunking", _safe_variable_get("demo_limit_chunking", "50")
    ), 50)

    if demo_mode:
        logger.info(f"Demo mode ON: limiting chunking to {demo_limit} docs")
        original_sql = chunking_pipeline_mod.FETCH_SQL
        chunking_pipeline_mod.FETCH_SQL = original_sql.rstrip().rstrip(';') + f"\nLIMIT {demo_limit}"

    try:
        run_chunking_pipeline()
    finally:
        if demo_mode:
            chunking_pipeline_mod.FETCH_SQL = original_sql

    logger.info("Chunking pipeline completed.")


def embeddings_task(**kwargs):
    """Run the embeddings pipeline with optional demo limits."""
    dag_run = kwargs.get("dag_run")
    run_conf = dag_run.conf if dag_run and isinstance(dag_run.conf, dict) else {}

    demo_mode = _as_bool(run_conf.get(
        "demo_mode", _safe_variable_get("demo_mode", "false")
    ))
    demo_limit = _as_int(run_conf.get(
        "demo_limit_embeddings", _safe_variable_get("demo_limit_embeddings", "50")
    ), 50)

    if demo_mode:
        logger.info(f"Demo mode ON: limiting embeddings to {demo_limit} chunks")
        original_func = embeddings_pipeline_mod.fetch_chunks_missing_embeddings

        def limited_fetch(conn, models):
            chunks = original_func(conn, models)
            logger.info(f"Demo: truncating {len(chunks)} chunks to {demo_limit}")
            return chunks[:demo_limit]

        embeddings_pipeline_mod.fetch_chunks_missing_embeddings = limited_fetch

    try:
        run_embeddings_pipeline()
    finally:
        if demo_mode:
            embeddings_pipeline_mod.fetch_chunks_missing_embeddings = original_func

    logger.info("Embeddings pipeline completed.")


def build_email_body(**kwargs):
    """Build HTML email body reporting chunking and embedding task outcomes."""
    ti = kwargs['ti']
    dag_run = kwargs['dag_run']

    failed_tasks = [
        t.task_id for t in dag_run.get_task_instances()
        if t.state == 'failed'
    ]
    status = 'FAILED' if failed_tasks else 'SUCCESS'

    chunks_created = ti.xcom_pull(task_ids='run_chunking', key='chunks_created') or 'N/A'
    embeddings_generated = ti.xcom_pull(task_ids='run_embeddings', key='embeddings_generated') or 'N/A'

    body = f"""
    <h2>InterviewPrep Chunking &amp; Embedding Pipeline — {status}</h2>
    <p><b>Run Date:</b> {kwargs.get('logical_date', 'N/A')}</p>

    <h3>Results</h3>
    <table border="1" cellpadding="5" cellspacing="0">
        <tr><th>Stage</th><th>Outcome</th><th>Count</th></tr>
        <tr>
            <td>Chunking</td>
            <td>{'FAILED' if 'run_chunking' in failed_tasks else 'SUCCESS'}</td>
            <td>{chunks_created}</td>
        </tr>
        <tr>
            <td>Embeddings</td>
            <td>{'FAILED' if 'run_embeddings' in failed_tasks else 'SUCCESS'}</td>
            <td>{embeddings_generated}</td>
        </tr>
    </table>
    """

    if failed_tasks:
        body += f"""
    <h3 style="color:red;">Failed Tasks</h3>
    <ul>{''.join(f'<li>{t}</li>' for t in failed_tasks)}</ul>
    """

    body += "<p>— InterviewPrep Airflow Pipeline</p>"

    subject = f"[InterviewPrep] Chunking & Embedding {status} — {kwargs.get('logical_date', '')}"
    ti.xcom_push(key='email_subject', value=subject)
    ti.xcom_push(key='email_body', value=body)
    return body


default_args = {
    'owner': 'admin',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'retries': 0,
}

dag = DAG(
    'chunking_embedding_pipeline',
    default_args=default_args,
    description='Chunk processed documents and generate vector embeddings',
    schedule=None,
    catchup=False,
    tags=['chunking', 'embeddings', 'production'],
)

start = BashOperator(
    task_id='start',
    bash_command='echo "Starting chunking & embedding pipeline at $(date)"',
    dag=dag,
)

run_chunking = PythonOperator(
    task_id='run_chunking',
    python_callable=chunking_task,
    execution_timeout=timedelta(hours=2),
    retries=2,
    retry_delay=timedelta(minutes=2),
    dag=dag,
)

run_embeddings = PythonOperator(
    task_id='run_embeddings',
    python_callable=embeddings_task,
    execution_timeout=timedelta(hours=4),
    retries=2,
    retry_delay=timedelta(minutes=5),
    dag=dag,
)

complete = BashOperator(
    task_id='complete',
    bash_command='echo "Chunking & embedding pipeline completed at $(date)"',
    dag=dag,
)

build_email = PythonOperator(
    task_id='build_email',
    python_callable=build_email_body,
    execution_timeout=timedelta(minutes=5),
    trigger_rule='all_done',
    dag=dag,
)

send_email = EmailOperator(
    task_id='send_notification_email',
    to=NOTIFY_EMAILS,
    subject="{{ ti.xcom_pull(task_ids='build_email', key='email_subject') }}",
    html_content="{{ ti.xcom_pull(task_ids='build_email', key='email_body') }}",
    trigger_rule='all_done',
    dag=dag,
)

start >> run_chunking >> run_embeddings >> complete >> build_email >> send_email