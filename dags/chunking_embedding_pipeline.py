from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta
import logging
import sys

sys.path.insert(0, '/home/dhruvkansara/airflow/dags')

from src.chunking.pipeline import run as run_chunking_pipeline
from src.embeddings.pipeline import run as run_embeddings_pipeline

logger = logging.getLogger("interviewprep.chunking_embedding_dag")


def chunking_task(**kwargs):
    """Run the chunking pipeline to split documents into chunks."""
    logger.info("Starting chunking pipeline...")
    run_chunking_pipeline()
    logger.info("Chunking pipeline completed.")


def embeddings_task(**kwargs):
    """Run the embeddings pipeline to generate vector embeddings for chunks."""
    logger.info("Starting embeddings pipeline...")
    run_embeddings_pipeline()
    logger.info("Embeddings pipeline completed.")


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

start >> run_chunking >> run_embeddings >> complete
