"""MapSet model and its one-line summary."""
import unittest

from height_hex_cutter.mapset import MapRef, MapSet


class Img:
    def __init__(self, name):
        self.name = name


class TestMapSet(unittest.TestCase):
    def test_summary_order_constants_packed_ignored(self):
        orm = Img("rock_arm_2k.png")
        ms = MapSet(maps={
            "Height": MapRef(Img("rock_disp.png")),
            "Metallic": MapRef(None, constant=0.0),
            "AO": MapRef(orm, chan="R"),
            "Base Color": MapRef(Img("rock_diff.png")),
            "Roughness": MapRef(orm, chan="G"),
        }, ignored=["x_emission.png", "x_opacity.png"])
        self.assertEqual(
            ms.summary(),
            "Base Color=rock_diff.png, AO=rock_arm_2k.png.R, Roughness=rock_arm_2k.png.G, "
            "Metallic=0 (constant), Height=rock_disp.png | ignored: x_emission.png, x_opacity.png")

    def test_constant_colour(self):
        ms = MapSet(maps={"Base Color": MapRef(None, constant=(0.5, 0.25, 1.0))})
        self.assertEqual(ms.summary(), "Base Color=(0.5, 0.25, 1) (constant)")

    def test_defaults_not_shared(self):
        a, b = MapSet(), MapSet()
        a.maps["AO"] = MapRef(Img("x"))
        a.ignored.append("y")
        a.principled["IOR"] = 1.4
        self.assertEqual((b.maps, b.ignored, b.principled), ({}, [], {}))
        r1, r2 = MapRef(Img("a")), MapRef(Img("b"))
        r1.chain.append("n")
        self.assertEqual(r2.chain, [])


if __name__ == "__main__":
    unittest.main()
