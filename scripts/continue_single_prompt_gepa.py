"""Historical sealed-Test scoring continuations are retired."""
import argparse
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    parser.error('HISTORICAL_SCORING_CONTINUATION_RETIRED; use a fresh current-scoring experiment and authorization')
if __name__=='__main__':main()
