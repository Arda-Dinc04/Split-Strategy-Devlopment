
import unittest
import sys
import os

# Add src directory to path (2 levels up from tests/)
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(os.path.dirname(current_dir), 'src')
sys.path.append(src_path)

from split_strategy.edgar.parsing import (
    check_compliance_flag,
    check_split_proposal_flag,
    extract_reverse_split_ratio,
    check_items
)

class TestEarlyWarningRegex(unittest.TestCase):

    def test_compliance_flag(self):
        # True positives
        self.assertTrue(check_compliance_flag("received a deficiency notice from Nasdaq"))
        self.assertTrue(check_compliance_flag("failure to maintain compliance with minimum bid price"))
        self.assertTrue(check_compliance_flag("ensure we regain compliance with NYSE listing standards"))
        
        # True negatives
        self.assertFalse(check_compliance_flag("we are in full compliance with all regulations"))
        self.assertFalse(check_compliance_flag("standard notice of meeting"))

    def test_split_proposal_flag(self):
        # True positives (from real filings)
        self.assertTrue(check_split_proposal_flag("Proposal to authorize the Board to effect a reverse stock split"))
        self.assertTrue(check_split_proposal_flag("approve an amendment to the Certificate of Incorporation to effect a reverse stock split"))
        self.assertTrue(check_split_proposal_flag("grant the Board discretionary authority to effect a reverse stock split"))
        self.assertTrue(check_split_proposal_flag("reverse split ratio of not less than 1-for-2 and not more than 1-for-50"))
        
        # True negatives
        self.assertFalse(check_split_proposal_flag("reverse stock split that became effective on May 24, 2024")) # Past tense context
        self.assertFalse(check_split_proposal_flag("effect on the outcome of this proposal"))
    
    def test_ratio_extraction(self):
        self.assertEqual(extract_reverse_split_ratio("1-for-150 reverse stock split")['ratio_den'], 150)
        self.assertEqual(extract_reverse_split_ratio("1 for 20 reverse split")['ratio_den'], 20)
        self.assertEqual(extract_reverse_split_ratio("ratio of 1:50")['ratio_den'], 50)
        
        # Should not match forward split or 1:1
        self.assertIsNone(extract_reverse_split_ratio("2-for-1 stock split"))


if __name__ == '__main__':
    unittest.main()
