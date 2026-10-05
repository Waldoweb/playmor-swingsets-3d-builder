"""Geometry and attachment checks: python3 tools/test_turbo_twister.py."""

import hashlib
import json
import math
from pathlib import Path
import unittest

import numpy as np
import turbo_twister as slide


class FiveFootTubeTests(unittest.TestCase):
    def test_photo_handedness_and_return_bend(self):
        stations, _, _ = slide.path(1.329, height=5)
        p = np.array([(u, w, y) for u, w, y, _, _ in stations])
        # Facing the entrance from the yard: +w is left. The entrance must
        # be right of the exit, and the lower elbow must return from the
        # furthest-left point. A mirror or a diagonal dogleg fails this.
        self.assertGreater(p[-1, 1], 0.25)
        self.assertGreater(p[:, 1].max() - p[-1, 1], 0.5)
        self.assertTrue(np.all(p[:, 0] >= -1e-6))
        self.assertGreater(p[-1, 0] - p[-2, 0], 0)
        self.assertLess(p[-1, 1] - p[-2, 1], 0)
        self.assertTrue(np.all(np.diff(p[:, 2]) <= 0))
        self.assertAlmostEqual(p[-1, 2] - (slide.R_OUT - slide.WALL), slide.BED)

    def test_mesh_is_finite_and_foot_meets_ground(self):
        tube, bolts = slide.build(1.329, height=5)
        for mesh in (tube, bolts):
            v, n, f = mesh.arrays()
            self.assertTrue(np.isfinite(v).all())
            self.assertTrue(np.isfinite(n).all())
            self.assertTrue((f < len(v)).all())
            np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1, atol=1e-6)
        self.assertAlmostEqual(tube.arrays()[0][:, 2].min(), 0)

    def test_published_asset_and_saved_design_attachment(self):
        models = Path(slide.MODELS)
        manifest = json.loads((models / 'manifest.json').read_text())
        entry = manifest['products']['TTWS-5']['files'][0]
        asset = models / entry['file']
        raw = asset.read_bytes()
        self.assertEqual(asset.name, 'TTWS-5.' + hashlib.sha256(raw).hexdigest()[:8] + '.glb')
        self.assertEqual(len(raw), entry['bytes'])
        gltf, _ = slide.read_glb(asset)
        world = slide.world_matrices(gltf)
        joints = [(i, n) for i, n in enumerate(gltf['nodes'])
                  if n.get('name', '').startswith('joint')]
        self.assertEqual(len(joints), 1)
        i, joint = joints[0]
        self.assertEqual(joint['name'], 'joint_c,1,6')
        np.testing.assert_allclose(world[i][:3, 3], [.551, 1.829, 0], atol=1e-6)
        root = gltf['nodes'][gltf['scenes'][gltf.get('scene', 0)]['nodes'][0]]
        self.assertIn('mirrorx', root['name'])
        # Retain the root's original half-turn; moving it would reverse
        # the named joint's facing in existing saved designs.
        np.testing.assert_allclose(slide.local_matrix(root)[:3, :3],
                                   np.diag([-1, 1, -1]), atol=1e-6)


if __name__ == '__main__':
    unittest.main()
