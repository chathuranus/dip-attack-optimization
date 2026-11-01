
import random
import unittest

from sll_algorithm3 import (
    postdominators,
    select_sll
)


class TestShortcut(unittest.TestCase):
    def test_dominators_are_all_paths(self):
        gates = [
            ('buf', 'n1', ['a']),
            ('and', 'n2', ['n1', 'b']),
            ('or', 'y', ['n2', 'c']),
            ('buf', 'z', ['n1'])
        ]
        pd, reachable = postdominators(gates, ['y', 'z'])
        self.assertTrue(reachable['n1'])
        self.assertNotIn('n2', pd['n1'])  # path n1->z bypasses n2
        self.assertIn('n2', pd['n2'])
        self.assertIn('y', pd['n2'])

    def test_retry_rejected_does_not_reduce_selected(self):
        gates = [
            ('buf', 'n1', ['a']),
            ('buf', 'n2', ['b']),
            ('or', 'n3', ['n1', 'n2']),
            ('buf', 'y', ['n3'])
        ]
        strict = select_sll(
            gates, ['a', 'b'], ['y'], 4, random.Random(0),
            atpg_backend='exhaustive'
        )
        retry = select_sll(
            gates, ['a', 'b'], ['y'], 4, random.Random(0),
            atpg_backend='exhaustive',
            retry_rejected=True
        )
        self.assertLessEqual(len(strict.locations), 4)
        self.assertEqual(len(retry.locations), 4)
        self.assertEqual(len(set(retry.locations)), 4)

    def test_shortcut_same_result_for_small(self):
        gates = [
            ('buf', 'n1', ['a']),
            ('buf', 'n2', ['b']),
            ('and', 'n3', ['n1', 'n2']),
            ('xor', 'n4', ['n3', 'c']),
            ('buf', 'y', ['n4'])
        ]
        for retry in [False, True]:
            a = select_sll(
                gates, ['a', 'b', 'c'], ['y'], 5,
                random.Random(3),
                atpg_backend='exhaustive',
                use_theorem1=True,
                retry_rejected=retry
            )
            b = select_sll(
                gates, ['a', 'b', 'c'], ['y'], 5,
                random.Random(3),
                atpg_backend='exhaustive',
                use_theorem1=False,
                retry_rejected=retry
            )
            self.assertEqual(a.locations, b.locations)


if __name__ == '__main__':
    unittest.main()
