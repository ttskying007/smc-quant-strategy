#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

INTERESTS_FILE = Path("/root/.hermes/skills/interest_points.json")

def load_interests():
    with open(INTERESTS_FILE) as f:
        return json.load(f)

def save_interests(interests):
    with open(INTERESTS_FILE, "w") as f:
        json.dump(interests, f, indent=2, ensure_ascii=False)

def list_interests(interests):
    print("//n//[Interest Points]")
    print("-" * 60)
    for key, data in sorted(interests.items(), key=lambda x: -x[1]["priority"]):
        status = "ACTIVE" if data.get("active", True) else "INACTIVE"
        print(f"  [{key}] {status}")
        print(f"    Name: {data['name']}")
        print(f"    Priority: {data['priority']}")
        print(f"    Keywords: {', '.join(data['keywords'])}")
        print(f"    Description: {data['description']}")
        print()

if __name__ == "__main__":
    interests = load_interests()
    list_interests(interests)
