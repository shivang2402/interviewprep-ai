from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.exceptions import AirflowFailException
from datetime import datetime, timedelta
import logging
import sys

sys.path.insert(0, '/home/dhruvkansara/airflow/dags')

from src.scrapers.gfg import GFGScraper
from src.scrapers.leetcode import LeetCodeScraper
from src.scrapers.medium import MediumScraper
from src.storage.gcs_backend import GCSBackend
from google.cloud import storage as gcs

logger = logging.getLogger("interviewprep.dag")

GCS_BUCKET_NAME = 'interviewprep-ai-data'
GCP_PROJECT_ID = 'professorbot-dovbsg'


def _get_batch_id(**kwargs) -> str:
    """Build batch_id from Airflow execution date (e.g., 2026-02-22_bulk)."""
    execution_date = kwargs.get("logical_date", datetime.utcnow())
    return f"{execution_date.strftime('%Y-%m-%d')}_bulk"


def _count_blobs(prefix: str, suffix: str = ".json") -> int:
    """Count blobs under a given GCS prefix with optional suffix filter."""
    client = gcs.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blobs = list(bucket.list_blobs(prefix=prefix, max_results=5000))
    if suffix:
        return sum(1 for b in blobs if b.name.endswith(suffix))
    return len(blobs)


def scrape_geeksforgeeks(**kwargs):
    print("=" * 60)
    print("Starting GFG scraper - BULK MODE")
    print("=" * 60)
    storage = GCSBackend(bucket_name=GCS_BUCKET_NAME, project_id=GCP_PROJECT_ID)
    scraper = GFGScraper(
        scrape_type='bulk',
        storage=storage
    )
    scraper.run()
    print(f"GFG Complete: {scraper.stats['files_collected']} files")
    return scraper.stats


def scrape_leetcode(**kwargs):
    print("=" * 60)
    print("Starting LeetCode scraper - BULK MODE")
    print("=" * 60)
    storage = GCSBackend(bucket_name=GCS_BUCKET_NAME, project_id=GCP_PROJECT_ID)
    scraper = LeetCodeScraper(
        scrape_type='bulk',
        storage=storage,
        fetch_comments=False
    )
    scraper.run()
    print(f"LeetCode Complete: {scraper.stats['files_collected']} files")
    return scraper.stats


def scrape_medium(**kwargs):
    print("=" * 60)
    print("Starting Medium scraper - BULK MODE")
    print("=" * 60)
    storage = GCSBackend(bucket_name=GCS_BUCKET_NAME, project_id=GCP_PROJECT_ID)
    scraper = MediumScraper(
        scrape_type='bulk',
        storage=storage,
        log_dir='/tmp/medium_logs'
    )
    scraper.run()
    print(f"Medium Complete: {scraper.stats['success']} files")
    return scraper.stats


def print_summary(**kwargs):
    ti = kwargs['ti']
    gfg_stats = ti.xcom_pull(task_ids='scrape_gfg') or {}
    leetcode_stats = ti.xcom_pull(task_ids='scrape_leetcode') or {}
    medium_stats = ti.xcom_pull(task_ids='scrape_medium') or {}
    
    total = (
        gfg_stats.get('files_collected', 0) +
        leetcode_stats.get('files_collected', 0) +
        medium_stats.get('success', 0)
    )
    
    print("\n" + "=" * 60)
    print("BULK SCRAPING PIPELINE SUMMARY")
    print("=" * 60)
    print(f"GeeksforGeeks: {gfg_stats.get('files_collected', 0)} files")
    print(f"LeetCode:      {leetcode_stats.get('files_collected', 0)} files")
    print(f"Medium:        {medium_stats.get('success', 0)} files")
    print(f"TOTAL:         {total} files")
    print("=" * 60)
    
    return {
        'total_files': total,
        'gfg': gfg_stats,
        'leetcode': leetcode_stats,
        'medium': medium_stats
    }



def run_preprocessing(**kwargs):
    """Run preprocessing pipeline on raw scraped data. Uses resume on retry."""
    # Lazy import to avoid loading NLP models at DAG parse time
    import src.preprocessing.steps  # noqa: F401
    from src.preprocessing.pipeline import PreprocessingPipeline

    batch_id = _get_batch_id(**kwargs)
    is_retry = kwargs.get("ti").try_number > 1

    logger.info(
        f"Starting preprocessing for batch '{batch_id}' "
        f"(retry={is_retry}, resume={is_retry})"
    )

    pipeline = PreprocessingPipeline()
    report = pipeline.run(batch_id=batch_id, resume=is_retry)

    ti = kwargs["ti"]
    ti.xcom_push(key="preprocess_status", value=report.status)
    ti.xcom_push(key="preprocess_input_count", value=report.input_count)
    ti.xcom_push(key="preprocess_output_count", value=report.output_count)
    ti.xcom_push(key="preprocess_duration_seconds", value=report.total_duration_seconds)

    if report.status != "completed":
        raise AirflowFailException(
            f"Preprocessing failed for batch '{batch_id}'. "
            f"Input={report.input_count}, Output={report.output_count}. "
            f"Check report: processed/{batch_id}_report.json"
        )

    print("\n" + "=" * 60)
    print("PREPROCESSING SUMMARY")
    print("=" * 60)
    print(f"Batch:        {batch_id}")
    print(f"Input docs:   {report.input_count}")
    print(f"Output docs:  {report.output_count}")
    print(f"Duration:     {report.total_duration_seconds:.1f}s")
    print(f"Steps run:    {len(report.step_results)}")
    print("=" * 60)

    return report.to_dict()

def validate_processed_data(**kwargs):
    """Verify processed data exists in GCS and counts match."""
    ti = kwargs["ti"]
    batch_id = _get_batch_id(**kwargs)

    preprocess_output = ti.xcom_pull(
        task_ids="run_preprocessing", key="preprocess_output_count"
    ) or 0

    processed_prefix = f"processed/{batch_id}/"
    gcs_count = _count_blobs(processed_prefix)

    report_path = f"processed/{batch_id}_report.json"
    report_exists = _count_blobs(report_path, suffix=None) > 0

    print("\n" + "=" * 60)
    print(f"PROCESSED DATA VALIDATION — batch: {batch_id}")
    print("=" * 60)
    print(f"  Pipeline reported:  {preprocess_output} docs")
    print(f"  GCS blob count:     {gcs_count}")
    print(f"  Report exists:      {report_exists}")

    errors = []

    if gcs_count == 0:
        errors.append(
            f"No processed files found at processed/{batch_id}/"
        )

    if preprocess_output > 0 and gcs_count != preprocess_output:
        errors.append(
            f"Count mismatch: pipeline reported {preprocess_output} "
            f"but GCS has {gcs_count} blobs"
        )

    if not report_exists:
        errors.append(f"Pipeline report not found at {report_path}")

    if errors:
        error_msg = "; ".join(errors)
        raise AirflowFailException(
            f"Processed data validation failed: {error_msg}"
        )

    print("\nProcessed data validated successfully.")



def load_to_database(**kwargs):
    """Load processed documents from GCS into PostgreSQL."""
    import os
    import json
    import psycopg2
    from src.database.loader import BatchDBLoader

    batch_id = _get_batch_id(**kwargs)
    storage = GCSBackend(bucket_name=GCS_BUCKET_NAME, project_id=GCP_PROJECT_ID)

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "34.148.0.165"),
        dbname=os.environ.get("DB_NAME", "interviewprep-ai-database"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "admin"),
        port=int(os.environ.get("DB_PORT", "5432")),
        sslmode="require",
    )

    loader = BatchDBLoader(gcs_backend=storage, db_conn=conn, batch_size=50)
    prefix = f"processed/{batch_id}/"
    result = loader.load_batch(prefix)

    ti = kwargs["ti"]
    ti.xcom_push(key="db_inserted", value=result["inserted"])
    ti.xcom_push(key="db_skipped", value=result["skipped"])

    print("\n" + "=" * 60)
    print("DATABASE LOAD SUMMARY")
    print("=" * 60)
    print(f"  Batch:     {batch_id}")
    print(f"  Inserted:  {result['inserted']}")
    print(f"  Skipped:   {result['skipped']}")
    print(f"  Errors:    {len(result['errors'])}")
    print("=" * 60)

    conn.close()

    if result["inserted"] == 0 and result["total"] > 0:
        raise AirflowFailException(
            f"DB load failed: 0 inserted out of {result['total']} files"
        )

    return result



default_args = {
    'owner': 'admin',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'retries': 0,
}

dag = DAG(
    'interview_scraping_pipeline',
    default_args=default_args,
    description='Scrape interview experiences, preprocess, and validate',
    schedule=None,
    catchup=False,
    tags=['scraping', 'preprocessing', 'bulk', 'production'],
)

start = BashOperator(
    task_id='start',
    bash_command='echo " Starting BULK scraping at $(date)"',
    dag=dag,
)

scrape_gfg = PythonOperator(
    task_id='scrape_gfg',
    python_callable=scrape_geeksforgeeks,
    execution_timeout=timedelta(hours=24),
    dag=dag,
)

scrape_leetcode = PythonOperator(
    task_id='scrape_leetcode',
    python_callable=scrape_leetcode,
    execution_timeout=timedelta(hours=24),
    dag=dag,
)

scrape_medium = PythonOperator(
    task_id='scrape_medium',
    python_callable=scrape_medium,
    execution_timeout=timedelta(hours=24),
    dag=dag,
)

summary = PythonOperator(
    task_id='print_summary',
    python_callable=print_summary,
    execution_timeout=timedelta(hours=1),
    dag=dag,
)

preprocess = PythonOperator(
    task_id='run_preprocessing',
    python_callable=run_preprocessing,
    execution_timeout=timedelta(hours=4),
    retries=3,
    retry_delay=timedelta(minutes=2),
    dag=dag,
)

validate = PythonOperator(
    task_id='validate_processed_data',
    python_callable=validate_processed_data,
    execution_timeout=timedelta(minutes=10),
    dag=dag,
)

db_load = PythonOperator(
    task_id='load_to_database',
    python_callable=load_to_database,
    execution_timeout=timedelta(hours=2),
    retries=2,
    retry_delay=timedelta(minutes=2),
    dag=dag,
)

complete = BashOperator(
    task_id='complete',
    bash_command='echo " Pipeline completed at $(date)"',
    dag=dag,
)

start >> [scrape_gfg, scrape_leetcode, scrape_medium] >> summary >> preprocess >> validate >> db_load >> complete