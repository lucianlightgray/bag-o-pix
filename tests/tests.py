import unittest
import cv2
import numpy as np
import os
import sys

# Add the project root to sys.path to import MainWindow
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# We need a dummy QApplication for PyQt widgets
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from main import MainWindow

class TestLogoDetection(unittest.TestCase):
    def test_logo_region_detection(self):
        self.window = MainWindow()
        self.base_path = os.path.join('tests', 'images', 'Flowers-base.png')
        self.edit_paths = [
            os.path.join('tests', 'images', f'Flowers-edit{i}.png') for i in range(1, 5)
        ]
        
        self.window.set_base_image(self.base_path)
        for path in self.edit_paths:
            self.window.append_edited_image(path)
        
        self.window.analyze_differences()
        
        print(f"Number of found regions: {len(self.window.found_regions)}")
        for i, region in enumerate(self.window.found_regions):
            x, y, w, h = region['rect']
            print(f"Region {i}: Rect ({x}, {y}, {w}, {h}), Area: {region['area']}")
        
        # The logo is in the bottom-left. 
        # Image size is 896x1344 (WxH), so shape is (1344, 896).
        # Logo area is roughly [1144:1344, 0:200]
        logo_area_slice = (slice(1144, 1344), slice(0, 200))
        
        found = False
        max_logo_area = 0
        for region in self.window.found_regions:
            mask_crop = region['mask'][logo_area_slice]
            area = cv2.countNonZero(mask_crop)
            if area > max_logo_area:
                max_logo_area = area
        
        print(f"Max detected logo mask area in target slice: {max_logo_area}")
        self.assertGreater(max_logo_area, 1000, f"Logo region not fully captured (mask area {max_logo_area} < 1000)")

    def test_startrek_detection(self):
        self.window = MainWindow()
        self.base_path = os.path.join('tests', 'images', 'startrek-base.png')
        self.edit_paths = [
            os.path.join('tests', 'images', f'startrek-edit{i}.png') for i in range(1, 5)
        ]
        
        self.window.set_base_image(self.base_path)
        for path in self.edit_paths:
            self.window.append_edited_image(path)
        
        self.window.analyze_differences()
        
        print(f"Star Trek: Number of found regions: {len(self.window.found_regions)}")
        self.assertGreater(len(self.window.found_regions), 0, "No regions found in Star Trek images")

if __name__ == '__main__':
    unittest.main()
