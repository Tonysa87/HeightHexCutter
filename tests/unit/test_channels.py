"""File-name channel detection (pure Python, no Blender)."""
import unittest

from height_hex_cutter.channels import IMAGE_EXTS, detect_channel

CASES = {
    "T_rock_4K_BaseColor.png": ("Base Color", False),
    "rock_diff_2k.jpg": ("Base Color", False),
    "Ground_Color.png": ("Base Color", False),
    "x_albedo.tga": ("Base Color", False),
    "T_sjgkfiok_4K_Diffuse.png": ("Base Color", False),
    "T_uddkdbuya_4K_B.png": ("Base Color", False),        # Megascans / Fab glTF export
    "T_rock_4K_AO.png": ("AO", False),
    "Ground_AmbientOcclusion.png": ("AO", False),
    "T_rock_4K_Roughness.png": ("Roughness", False),
    "gray_rocks_rough_4k.exr": ("Roughness", False),
    "T_rock_4K_Metallic.png": ("Metallic", False),
    "x_metalness.png": ("Metallic", False),
    "wine_barrel_01_metal_1k.exr": ("Metallic", False),
    "T_rock_4K_Normal.png": ("Normal", False),
    "rock_nor_gl_2k.png": ("Normal", False),
    "Ground_NormalGL.png": ("Normal", False),
    "bark_NormalDX.png": ("Normal", True),
    "x_normal_dx.png": ("Normal", True),
    "rock_nor_dx_2k.exr": ("Normal", True),
    "T_rock_4K_Height.png": ("Height", False),
    "rock_disp_2k.png": ("Height", False),
    "x_Displacement.png": ("Height", False),
    "x_bump.png": ("Height", False),
    "rock_arm_2k.png": ("ORM", False),
    "x_ORM.png": ("ORM", False),
    "x_H.png": ("Height", False),
    "x_N.png": ("Normal", False),
    "x_R.png": ("Roughness", False),
    "x_M.png": ("Metallic", False),
}


class TestDetect(unittest.TestCase):
    def test_detect_common_sets(self):
        for name, want in CASES.items():
            with self.subTest(name=name):
                self.assertEqual(detect_channel(name), want)

    def test_detect_ignored(self):
        for name in ("x_emission.png", "x_opacity.png", "x_specular.png", "x_sss.png", "x_translucency.png"):
            with self.subTest(name=name):
                self.assertEqual(detect_channel(name), (None, False))

    def test_detect_ambiguous(self):
        for name in ("rock_4k.png", "T_Bark_D.png", "2048.png", "rock_v2.png", "tex_1024x1024.png"):
            with self.subTest(name=name):
                self.assertEqual(detect_channel(name)[0], None)
        # resolution / version tokens never decide, wherever they are
        self.assertEqual(detect_channel("4k_rock_v2_rough_2048.png")[0], "Roughness")

    def test_asset_words_do_not_beat_the_suffix(self):
        cases = {
            "T_Rusty_Metal_4K_B.png": "Base Color",
            "T_Rough_Stone_4K_N.png": "Normal",
            "T_Forest_Ground_Base_4K_N.png": "Normal",
            "T_Color_Tiles_4K_H.png": "Height",
            "RustyMetalAlbedo.png": "Base Color",
            "RoughStoneColor.png": "Base Color",
            "RockOcclusionRoughnessMetallic.png": "ORM",
            "metal_plate_diff.png": "Base Color",
        }
        for name, want in cases.items():
            with self.subTest(name=name):
                self.assertEqual(detect_channel(name)[0], want)

    def test_ignored_channel_words(self):
        for name in ("leaf_translucency_color.png", "x_emissive_color.png", "metal_plate_preview.png",
                     "rock_specular_color.png", "bark_opacity_mask.png", "rock_gloss.png"):
            with self.subTest(name=name):
                self.assertEqual(detect_channel(name)[0], None)

    def test_case_and_extensions(self):
        self.assertEqual(detect_channel("ROCK_ROUGHNESS.PNG")[0], "Roughness")
        self.assertEqual(detect_channel("E:\\tex\\set_4k\\rock_Normal.png")[0], "Normal")
        self.assertEqual(detect_channel("/mnt/e/tex/normal_maps/rock_AO.png")[0], "AO")   # folders ignored
        for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".tga", ".bmp", ".webp"):
            self.assertIn(ext, IMAGE_EXTS)


if __name__ == "__main__":
    unittest.main()
