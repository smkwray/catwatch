#!/usr/bin/env python3
from opencatwatch.config import get_settings
from opencatwatch.pipelines.quality import audit_processed_data


if __name__ == "__main__":
    print(audit_processed_data(get_settings()))
