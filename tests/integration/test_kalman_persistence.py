import unittest
import os
import sqlite3
import json
from src.services.arbitrage_service import ArbitrageService
from src.models.persistence import PersistenceManager
from src.config import settings
from src.services.kalman_service import KalmanFilter

class TestKalmanPersistence(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_kalman.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.persistence = PersistenceManager(self.db_path)
        self.service = ArbitrageService(persistence=self.persistence)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_save_and_reload_state(self):
        pair_id = "test_pair_123"
        kf = KalmanFilter(delta=1e-5, r=0.01)
        
        # 1. Update filter to change state from default [0.0, 1.0]
        kf.update(price_a=105.0, price_b=100.0)
        initial_alpha, initial_beta = kf.state
        
        # 2. Save state
        self.service.save_filter_state(pair_id, kf, innovation_var=0.5)
        
        # 3. Create new service instance to simulate restart
        new_service = ArbitrageService(persistence=self.persistence)
        
        # 4. Get filter - should reload from DB
        new_kf = new_service.get_or_create_filter(pair_id)
        
        reload_alpha, reload_beta = new_kf.state
        self.assertAlmostEqual(initial_alpha, reload_alpha)
        self.assertAlmostEqual(initial_beta, reload_beta)
        self.assertEqual(new_kf.R, 0.01)

    def test_fresh_initialization_when_no_state(self):
        pair_id = "brand_new_pair"
        # Should initialize with provided seeds
        kf = self.service.get_or_create_filter(pair_id, initial_state=[0.1, 1.2])
        self.assertEqual(kf.state[0], 0.1)
        self.assertEqual(kf.state[1], 1.2)

if __name__ == '__main__':
    unittest.main()
