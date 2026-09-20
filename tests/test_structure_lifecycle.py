"""Causal structure-state regressions; artificial paths are not market evidence."""
import unittest
from unittest.mock import patch

from lab.structure import build_structure_features
from lab.smt import relative_strength_divergence


def bars(prices):
    return [dict(ts=1_700_000_000_000+i*900000, open=p, high=p+.2,
                 low=p-.2, close=p) for i,p in enumerate(prices)]


class StructureLifecycleTests(unittest.TestCase):
    def test_invalidated_gap_cannot_reappear_after_more_than_25_new_gaps(self):
        rows=bars([100+i for i in range(40)]+[95])
        result=build_structure_features(rows,[1.]*len(rows))
        self.assertFalse(result[-1]['bull_fvg_active'])
        self.assertIsNone(result[-1]['bull_fvg_mid'])

    def test_inverse_gap_retires_after_close_back_through_original_zone(self):
        rows=bars([100,101,103,99,104])
        result=build_structure_features(rows,[1.]*len(rows))
        self.assertTrue(result[3]['bear_ifvg_active'])
        self.assertFalse(result[4]['bear_ifvg_active'])

    def test_unfilled_gaps_expire_and_bearish_inversions_are_symmetric(self):
        rows=bars([100,101]+[103]*245)
        result=build_structure_features(rows,[1.]*len(rows))
        self.assertTrue(result[10]['bull_fvg_active'])
        self.assertFalse(result[-1]['bull_fvg_active'])
        rows=bars([104,103,101,105,100])
        result=build_structure_features(rows,[1.]*len(rows))
        self.assertTrue(result[3]['bull_ifvg_active'])
        self.assertFalse(result[4]['bull_ifvg_active'])

    def test_a_consumed_swing_does_not_report_a_fresh_break_each_bar(self):
        rows=bars([100]*10+[102,103,104])
        highs=[False]*len(rows);highs[6]=True
        with patch('lab.structure._swing_flags',return_value=(highs,[False]*len(rows))):
            result=build_structure_features(rows,[1.]*len(rows))
        self.assertEqual([r['bos_up'] for r in result[10:]],[True,False,False])
        self.assertEqual([r['bars_since_bos_up'] for r in result[10:]],[0,1,2])

    def test_future_prices_do_not_rewrite_past_structure(self):
        first=bars([100,101,103,99,104,102,105,97,110])
        full=first+bars([10]*5)
        for i,row in enumerate(full):row['ts']=first[0]['ts']+i*900000
        self.assertEqual(build_structure_features(first,[1.]*len(first)),
                         build_structure_features(full,[1.]*len(full))[:len(first)])

    def test_misaligned_peer_does_not_manufacture_divergence(self):
        primary=bars([100,101,102,103,104])
        peer=bars([100,101,102,103,104])[1:]
        result=relative_strength_divergence(primary,peer,lookback=2)
        self.assertEqual(len(result),len(primary))
        self.assertFalse(result[2]['smt_available'])
        self.assertTrue(result[3]['smt_available'])
        self.assertEqual(result[3]['smt_spread'],0.)

    def test_duplicate_or_unsorted_peer_timestamps_are_rejected(self):
        rows=bars([100,101,102,103])
        for peer in (rows[:2]+rows[1:],list(reversed(rows))):
            with self.subTest(peer=peer),self.assertRaises(ValueError):
                relative_strength_divergence(rows,peer,lookback=2)

    def test_later_peer_prices_cannot_change_earlier_spread(self):
        primary=bars([100,101,102,103,104]);peer=bars([100,101,101,102,103])
        old=relative_strength_divergence(primary[:4],peer[:4],lookback=2)
        self.assertEqual(old,relative_strength_divergence(primary,peer,lookback=2)[:4])


if __name__=='__main__':unittest.main()
