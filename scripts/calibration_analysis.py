import asyncio
import argparse
import logging
from src.services.latency_service import latency_service
from src.services.calibration_service import calibration_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description='Model Calibration Analysis CLI')
    parser.add_argument('--report', action='store_true', help='Generate latency performance report')
    parser.add_argument('--audit', type=int, metavar='DAYS', help='Run fill achievability audit for N days')
    
    args = parser.parse_args()
    
    if args.report:
        logger.info("Generating Latency Performance Report...")
        report = await latency_service.get_performance_report()
        print("\n=== Latency Performance Report ===")
        for k, v in report.items():
            print(f"{k:20}: {v}")
        print("==================================\n")
        
    if args.audit:
        logger.info(f"Running Fill Achievability Audit for last {args.audit} days...")
        audit = await calibration_service.run_fill_achievability_audit(args.audit)
        print("\n=== Fill Achievability Audit ===")
        for k, v in audit.items():
            print(f"{k:30}: {v}")
        print("================================\n")

if __name__ == "__main__":
    asyncio.run(main())
