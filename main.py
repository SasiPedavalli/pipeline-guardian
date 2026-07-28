"""
main.py

Run: python main.py

Loads the sample orders dataset, hands it to the PipelineGuardian agent,
and prints the AI-generated diagnosis.
"""

import pandas as pd
from agent import PipelineGuardian

EXPECTED_SCHEMA = {
    "order_id": "int64",
    "customer_id": "object",
    "order_date": "object",
    "amount": "float64",
    "region": "object",
}


def main():
    df = pd.read_csv("sample_data/orders.csv")

    guardian = PipelineGuardian(df)
    diagnosis = guardian.diagnose(
        dataset_description="Daily e-commerce orders feed landing in a raw ingestion table.",
        expected_schema=EXPECTED_SCHEMA,
    )

    print("\n" + "=" * 60)
    print("PIPELINEGUARDIAN DIAGNOSIS")
    print("=" * 60)
    print(diagnosis)


if __name__ == "__main__":
    main()
