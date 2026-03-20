#!/usr/bin/env python3
"""
Simple test runner for Stage 1 tests
Runs without pytest to avoid Python 3.14 compatibility issues
"""

import sys
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def run_tests():
    """Import and run Stage 1 tests"""
    passed = 0
    failed = 0
    
    print("=" * 60)
    print("Stage 1 Test Suite")
    print("=" * 60 + "\n")
    
    # Import test module
    try:
        from test_stage1 import (
            test_sentence_splitting,
            test_sentence_classification,
            test_pii_extraction,
            test_word_boundary_matching,
            test_stage1_validation
        )
    except ImportError as e:
        print(f"❌ Failed to import tests: {e}")
        return 1
    
    # Test list
    tests = [
        ("Sentence Splitting", test_sentence_splitting),
        ("Sentence Classification", test_sentence_classification),
        ("PII Extraction", test_pii_extraction),
        ("Word Boundary Matching", test_word_boundary_matching),
        ("Stage 1 Validation", test_stage1_validation),
    ]
    
    # Run tests
    for test_name, test_func in tests:
        try:
            print(f"Running: {test_name}...")
            test_func()
            print(f"  ✓ PASSED\n")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}\n")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            traceback.print_exc()
            print()
            failed += 1
    
    # Summary
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(run_tests())
