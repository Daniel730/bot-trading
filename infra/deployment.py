from src.monitor import monitor_flow
from prefect.deployments import Deployment
from prefect.client.schemas.schedules import CronSchedule
import os

def deploy():
    # Configure the deployment to run every 1 minute during NYSE hours
    # Monday to Friday, 14:30 to 21:00 WET
    # Note: Cron syntax is generic; refine based on your specific requirements
    schedule = CronSchedule(cron="*/1 14-21 * * 1-5", timezone="WET")

    deployment = Deployment.build_from_flow(
        flow=monitor_flow,
        name="Production Arbitrage Monitor",
        schedule=schedule,
        work_queue_name="koyeb-runner", # Name of the worker in Koyeb
        storage=None, # Code is already in the container
        path="/app", # Working directory in the container
        entrypoint="src/monitor.py:monitor_flow"
    )
    
    deployment.apply()
    print("Deployment 'Production Arbitrage Monitor' successfully applied to Prefect Cloud.")

if __name__ == "__main__":
    deploy()
