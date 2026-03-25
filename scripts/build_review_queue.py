#!/usr/bin/env python3
from opencatwatch.config import get_settings
from opencatwatch.pipelines.quality import build_manual_review_queue


if __name__ == "__main__":
    print(build_manual_review_queue(get_settings()))
