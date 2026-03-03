"""
test_scorecard_v37.py — Suite de tests para Winiw Quality Scorecard v3.7+
Ejecutar: WINIW_ADMIN_USER=test WINIW_ADMIN_PASS=test python -m unittest test_scorecard_v37 -v
Los tests usan SQLite in-memory — no tocan la BD de produccion.
"""

import unittest
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

os.environ.setdefault("WINIW_ADMIN_USER", "test_admin")
os.environ.setdefault("WINIW_ADMIN_PASS", "test_pass_seguro_123")

import amazon_scorecard_ultra_robust_v3_FINAL as sc


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_db():
    """BD SQLite in-memory con esquema completo."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    db_config = {"type": "sqlite", "_test_conn": conn}
    sc.init_database(db_config)
    return db_config, conn


# ─────────────────────────────────────────────────────────────────────────────
# 1. safe_number
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeNumber(unittest.TestCase):

    def test_integer(self):
        self.assertEqual(sc.safe_number(5), 5.0)

    def test_float_string(self):
        self.assertAlmostEqual(sc.safe_number("3.14"), 3.14)

    def test_comma_decimal(self):
        self.assertAlmostEqual(sc.safe_number("1,5"), 1.5)

    def test_none_returns_default(self):
        self.assertEqual(sc.safe_number(None), 0.0)

    def test_empty_string_returns_default(self):
        self.assertEqual(sc.safe_number(""), 0.0)

    def test_dash_returns_default(self):
        self.assertEqual(sc.safe_number("-"), 0.0)

    def test_nan_returns_default(self):
        self.assertEqual(sc.safe_number(float("nan")), 0.0)

    def test_custom_default(self):
        self.assertEqual(sc.safe_number(None, default=99.0), 99.0)

    def test_percent_stripped(self):
        self.assertAlmostEqual(sc.safe_number("95%"), 95.0)

    def test_negative(self):
        self.assertAlmostEqual(sc.safe_number("-2.5"), -2.5)

    def test_zero(self):
        self.assertEqual(sc.safe_number(0), 0.0)

    def test_large_number(self):
        self.assertEqual(sc.safe_number("1000"), 1000.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. safe_percentage
# ─────────────────────────────────────────────────────────────────────────────

class TestSafePercentage(unittest.TestCase):

    def test_percent_string(self):
        self.assertAlmostEqual(sc.safe_percentage("97.5%"), 0.975)

    def test_decimal_already(self):
        self.assertAlmostEqual(sc.safe_percentage("0.98"), 0.98, places=2)

    def test_empty_returns_1(self):
        self.assertEqual(sc.safe_percentage(""), 1.0)

    def test_none_returns_1(self):
        self.assertEqual(sc.safe_percentage(None), 1.0)

    def test_dash_returns_1(self):
        self.assertEqual(sc.safe_percentage("-"), 1.0)

    def test_100_percent(self):
        self.assertAlmostEqual(sc.safe_percentage("100%"), 1.0)

    def test_0_percent(self):
        self.assertAlmostEqual(sc.safe_percentage("0%"), 0.0)

    def test_integer_100(self):
        self.assertAlmostEqual(sc.safe_percentage(100), 1.0)

    def test_already_decimal_low(self):
        self.assertAlmostEqual(sc.safe_percentage(0.995), 0.995, places=3)


# ─────────────────────────────────────────────────────────────────────────────
# 3. clean_id
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanId(unittest.TestCase):

    def test_uppercase(self):
        self.assertEqual(sc.clean_id("amz001"), "AMZ001")

    def test_strips_spaces(self):
        self.assertEqual(sc.clean_id("  AMZ001  "), "AMZ001")

    def test_none_returns_string(self):
        self.assertIsInstance(sc.clean_id(None), str)

    def test_already_clean(self):
        self.assertEqual(sc.clean_id("AMZ123"), "AMZ123")

    def test_nan_handled(self):
        self.assertIsInstance(sc.clean_id(float("nan")), str)


# ─────────────────────────────────────────────────────────────────────────────
# 4. week_to_date
# ─────────────────────────────────────────────────────────────────────────────

class TestWeekToDate(unittest.TestCase):

    def test_standard_week(self):
        self.assertIsNotNone(sc.week_to_date("W07"))

    def test_zero_padded_equals_unpadded(self):
        self.assertEqual(sc.week_to_date("W07"), sc.week_to_date("W7"))

    def test_invalid_returns_none(self):
        self.assertIsNone(sc.week_to_date("INVALID"))

    def test_week_01(self):
        self.assertIsNotNone(sc.week_to_date("W01"))

    def test_week_52(self):
        self.assertIsNotNone(sc.week_to_date("W52"))


# ─────────────────────────────────────────────────────────────────────────────
# 5. hash_password / verify_password
# ─────────────────────────────────────────────────────────────────────────────

class TestPasswordHashing(unittest.TestCase):

    def test_hash_returns_string(self):
        self.assertIsInstance(sc.hash_password("mipassword"), str)

    def test_verify_correct(self):
        h = sc.hash_password("mipassword")
        self.assertTrue(sc.verify_password("mipassword", h))

    def test_verify_wrong(self):
        h = sc.hash_password("mipassword")
        self.assertFalse(sc.verify_password("otrapassword", h))

    def test_hash_unique_per_call(self):
        h1 = sc.hash_password("test123")
        h2 = sc.hash_password("test123")
        # bcrypt usa salt aleatorio — hashes distintos
        self.assertNotEqual(h1, h2)

    def test_long_password(self):
        h = sc.hash_password("a" * 72)
        self.assertTrue(sc.verify_password("a" * 72, h))

    def test_special_chars(self):
        pw = "P@$$w0rd!#%&*"
        h = sc.hash_password(pw)
        self.assertTrue(sc.verify_password(pw, h))


# ─────────────────────────────────────────────────────────────────────────────
# 6. init_database
# ─────────────────────────────────────────────────────────────────────────────

class TestInitDatabase(unittest.TestCase):

    def setUp(self):
        self.db, self.conn = make_db()

    def _tables(self):
        return [r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

    def test_creates_scorecards_table(self):
        self.assertIn("scorecards", self._tables())

    def test_creates_users_table(self):
        self.assertIn("users", self._tables())

    def test_creates_login_attempts_table(self):
        self.assertIn("login_attempts", self._tables())

    def test_creates_center_targets_table(self):
        self.assertIn("center_targets", self._tables())

    def test_superadmin_created(self):
        row = self.conn.execute(
            "SELECT username FROM users WHERE role='superadmin'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_idempotent(self):
        try:
            sc.init_database(self.db)
        except Exception as e:
            self.fail(f"Segunda llamada a init_database fallo: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. update_user_password
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateUserPassword(unittest.TestCase):

    def setUp(self):
        self.db, self.conn = make_db()
        self.conn.execute(
            "INSERT INTO users (username, password, role, active, must_change_password) "
            "VALUES ('jt_test', ?, 'jt', 1, 1)",
            (sc.hash_password("oldpass"),)
        )
        self.conn.commit()

    def test_update_returns_truthy(self):
        result = sc.update_user_password("jt_test", sc.hash_password("newpass"), self.db)
        self.assertIsNotNone(result)

    def test_new_password_verifiable(self):
        new_hash = sc.hash_password("newpass")
        sc.update_user_password("jt_test", new_hash, self.db)
        row = self.conn.execute(
            "SELECT password FROM users WHERE username='jt_test'"
        ).fetchone()
        self.assertTrue(sc.verify_password("newpass", row[0]))

    def test_must_change_cleared(self):
        sc.update_user_password("jt_test", sc.hash_password("newpass"), self.db)
        row = self.conn.execute(
            "SELECT must_change_password FROM users WHERE username='jt_test'"
        ).fetchone()
        self.assertEqual(row[0], 0)


# ─────────────────────────────────────────────────────────────────────────────
# 8. rate limiting
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimiting(unittest.TestCase):

    def setUp(self):
        self.db, self.conn = make_db()

    def test_not_locked_initially(self):
        self.assertFalse(sc.check_login_locked("nuevo_user", self.db))

    def test_record_attempt_no_crash(self):
        try:
            sc.record_login_attempt("user1", False, self.db)
        except Exception as e:
            self.fail(f"record_login_attempt lanzo excepcion: {e}")

    def test_locked_after_5_failures(self):
        for _ in range(6):
            sc.record_login_attempt("brute", False, self.db)
        self.assertTrue(sc.check_login_locked("brute", self.db))

    def test_success_resets_lock(self):
        for _ in range(4):
            sc.record_login_attempt("user2", False, self.db)
        sc.record_login_attempt("user2", True, self.db)
        self.assertFalse(sc.check_login_locked("user2", self.db))


# ─────────────────────────────────────────────────────────────────────────────
# 9. get_center_targets / save_center_targets
# ─────────────────────────────────────────────────────────────────────────────

class TestCenterTargets(unittest.TestCase):

    def setUp(self):
        self.db, self.conn = make_db()

    def test_get_targets_returns_dict(self):
        self.assertIsInstance(sc.get_center_targets("DIC1", db_config=self.db), dict)

    def test_default_targets_have_required_keys(self):
        targets = sc.get_center_targets("DIC1", db_config=self.db)
        for key in ["target_dnr", "target_dcr", "target_pod", "target_cc", "target_rts"]:
            self.assertIn(key, targets)

    def test_save_and_retrieve(self):
        custom = {
            "target_dnr": 1.0, "target_dcr": 0.99, "target_pod": 0.98,
            "target_cc": 0.97, "target_rts": 0.02, "target_cdf": 0.92,
            "target_fdps": 0.88
        }
        sc.save_center_targets("DIC1", custom, db_config=self.db)
        loaded = sc.get_center_targets("DIC1", db_config=self.db)
        self.assertAlmostEqual(loaded.get("target_dnr", -1), 1.0)
        self.assertAlmostEqual(loaded.get("target_dcr", -1), 0.99)

    def test_different_centers_independent(self):
        sc.save_center_targets("DIC1", {"target_dnr": 0.5}, db_config=self.db)
        sc.save_center_targets("DIC2", {"target_dnr": 2.0}, db_config=self.db)
        t1 = sc.get_center_targets("DIC1", db_config=self.db)
        t2 = sc.get_center_targets("DIC2", db_config=self.db)
        self.assertNotEqual(t1.get("target_dnr"), t2.get("target_dnr"))


# ─────────────────────────────────────────────────────────────────────────────
# 10. calculate_score_v3_robust
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateScore(unittest.TestCase):

    TARGETS = sc.Config.DEFAULT_TARGETS.copy()

    def _perfect(self):
        return pd.Series({
            "DNR": 0, "FS_Count": 0, "DCR": 1.0, "POD": 1.0,
            "CC": 1.0, "RTS": 0.0, "CDF": 1.0, "FDPS": 1.0,
            "DNR_RISK_EVENTS": 0, "Entregados": 200,
        })

    def _terrible(self):
        return pd.Series({
            "DNR": 12, "FS_Count": 25, "DCR": 0.80, "POD": 0.70,
            "CC": 0.70, "RTS": 0.20, "CDF": 0.60, "FDPS": 0.50,
            "DNR_RISK_EVENTS": 6, "Entregados": 50,
        })

    def test_perfect_score_high(self):
        score, _, _ = sc.calculate_score_v3_robust(self._perfect(), self.TARGETS)
        self.assertGreaterEqual(score, 85)

    def test_terrible_score_poor(self):
        _, cal, _ = sc.calculate_score_v3_robust(self._terrible(), self.TARGETS)
        self.assertEqual(cal, "🛑 POOR")

    def test_score_within_range(self):
        for row in [self._perfect(), self._terrible()]:
            score, _, _ = sc.calculate_score_v3_robust(row, self.TARGETS)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_returns_three_values(self):
        self.assertEqual(len(sc.calculate_score_v3_robust(self._perfect(), self.TARGETS)), 3)

    def test_dnr_penalizes(self):
        s_ok,  _, _ = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DNR": 0}), self.TARGETS)
        s_bad, _, _ = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DNR": 8}), self.TARGETS)
        self.assertGreater(s_ok, s_bad)

    def test_fs_penalizes(self):
        s_ok,  _, _ = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "FS_Count": 0}), self.TARGETS)
        s_bad, _, _ = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "FS_Count": 20}), self.TARGETS)
        self.assertGreater(s_ok, s_bad)

    def test_dcr_penalizes(self):
        s_ok,  _, _ = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DCR": 1.0}), self.TARGETS)
        s_bad, _, _ = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DCR": 0.90}), self.TARGETS)
        self.assertGreater(s_ok, s_bad)

    def test_calificacion_is_valid(self):
        valid = {"💎 FANTASTIC", "🥇 GREAT", "⚠️ FAIR", "🛑 POOR"}
        _, cal, _ = sc.calculate_score_v3_robust(self._perfect(), self.TARGETS)
        self.assertIn(cal, valid)
        _, cal2, _ = sc.calculate_score_v3_robust(self._terrible(), self.TARGETS)
        self.assertIn(cal2, valid)


# ─────────────────────────────────────────────────────────────────────────────
# 11. process_concessions
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessConcessions(unittest.TestCase):

    def _df(self, n=4):
        return pd.DataFrame({
            "Nombre del agente de entrega":              [f"Driver {i}" for i in range(n)],
            "ID de agente de entrega":                   [f"AMZ{i:03d}" for i in range(n)],
            "Paquetes entregados no recibidos (DNR)":    [i % 3 for i in range(n)],
            "Return to Station (RTS) - Porcentaje":      [f"{1+i*0.1:.1f}%" for i in range(n)],
            "Paquetes entregados":                       [100 + i*10 for i in range(n)],
        })

    def test_returns_dataframe(self):
        self.assertIsInstance(sc.process_concessions(self._df()), pd.DataFrame)

    def test_key_columns_present(self):
        result = sc.process_concessions(self._df())
        for col in ["ID", "Nombre", "DNR"]:
            self.assertIn(col, result.columns)

    def test_empty_input(self):
        self.assertIsInstance(sc.process_concessions(pd.DataFrame()), pd.DataFrame)

    def test_none_input(self):
        self.assertIsInstance(sc.process_concessions(None), pd.DataFrame)

    def test_dedup_by_id(self):
        df = pd.concat([self._df(3), self._df(3)], ignore_index=True)
        result = sc.process_concessions(df)
        self.assertEqual(len(result), 3)

    def test_dnr_capped_at_max(self):
        df = self._df(2)
        df.loc[0, "Paquetes entregados no recibidos (DNR)"] = 9999
        result = sc.process_concessions(df)
        self.assertLessEqual(result["DNR"].max(), sc.Config.MAX_DNR)


# ─────────────────────────────────────────────────────────────────────────────
# 12. process_quality
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessQuality(unittest.TestCase):

    def _df(self, n=3):
        return pd.DataFrame({
            "ID del transportista": [f"AMZ{i:03d}" for i in range(n)],
            "DCR": [f"{99-i:.1f}%" for i in range(n)],
            "POD": [f"{98-i:.1f}%" for i in range(n)],
            "CC":  [f"{97-i:.1f}%" for i in range(n)],
            "CDF": [f"{96-i:.1f}%" for i in range(n)],
        })

    def test_returns_dataframe(self):
        self.assertIsInstance(sc.process_quality(self._df()), pd.DataFrame)

    def test_key_columns(self):
        result = sc.process_quality(self._df())
        for col in ["ID", "DCR", "POD"]:
            self.assertIn(col, result.columns)

    def test_dcr_in_0_1_range(self):
        result = sc.process_quality(self._df())
        self.assertTrue((result["DCR"] >= 0).all())
        self.assertTrue((result["DCR"] <= 1.01).all())

    def test_empty(self):
        self.assertIsInstance(sc.process_quality(pd.DataFrame()), pd.DataFrame)

    def test_none(self):
        self.assertIsInstance(sc.process_quality(None), pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# 13. process_false_scan
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessFalseScan(unittest.TestCase):

    def _df(self):
        return pd.DataFrame({
            "Transporter ID":    ["AMZ001", "AMZ002", "AMZ003"],
            "False Scan Count":  [0, 2, 5],
        })

    def test_returns_dataframe(self):
        self.assertIsInstance(sc.process_false_scan(self._df()), pd.DataFrame)

    def test_columns(self):
        result = sc.process_false_scan(self._df())
        self.assertIn("ID", result.columns)
        self.assertIn("FS_Count", result.columns)

    def test_empty(self):
        self.assertIsInstance(sc.process_false_scan(pd.DataFrame()), pd.DataFrame)

    def test_none(self):
        self.assertIsInstance(sc.process_false_scan(None), pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# 14. merge_data_smart
# ─────────────────────────────────────────────────────────────────────────────

class TestMergeDataSmart(unittest.TestCase):

    def _conc(self, n=3):
        return pd.DataFrame({
            "ID": [f"AMZ{i:03d}" for i in range(n)],
            "Nombre": [f"Driver {i}" for i in range(n)],
            "DNR": [i for i in range(n)],
            "RTS": [0.01] * n,
            "Entregados": [100] * n,
        })

    def _qual(self, n=3):
        return pd.DataFrame({
            "ID": [f"AMZ{i:03d}" for i in range(n)],
            "DCR": [0.99] * n, "POD": [0.98] * n,
            "CC": [0.97] * n,  "CDF": [0.95] * n,
        })

    def test_returns_dataframe(self):
        self.assertIsInstance(sc.merge_data_smart(self._conc(), self._qual()), pd.DataFrame)

    def test_preserves_base_count(self):
        result = sc.merge_data_smart(self._conc(5), self._qual(5))
        self.assertEqual(len(result), 5)

    def test_quality_columns_merged(self):
        result = sc.merge_data_smart(self._conc(), self._qual())
        self.assertIn("DCR", result.columns)

    def test_none_quality_handled(self):
        result = sc.merge_data_smart(self._conc(), None)
        self.assertEqual(len(result), 3)

    def test_all_optional_none(self):
        result = sc.merge_data_smart(self._conc(), None, None, None, None)
        self.assertIsInstance(result, pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# 15. get_user_centro / set_user_centro
# ─────────────────────────────────────────────────────────────────────────────

class TestUserCentro(unittest.TestCase):

    def setUp(self):
        self.db, self.conn = make_db()
        self.conn.execute(
            "INSERT INTO users (username, password, role, active, must_change_password) "
            "VALUES ('jt_test', 'hash', 'jt', 1, 0)"
        )
        self.conn.commit()

    def test_get_centro_none_initially(self):
        self.assertIsNone(sc.get_user_centro("jt_test", self.db))

    def test_set_and_get_centro(self):
        sc.set_user_centro("jt_test", "DIC1", self.db)
        self.assertEqual(sc.get_user_centro("jt_test", self.db), "DIC1")

    def test_set_none_clears(self):
        sc.set_user_centro("jt_test", "DIC1", self.db)
        sc.set_user_centro("jt_test", None, self.db)
        self.assertIsNone(sc.get_user_centro("jt_test", self.db))

    def test_nonexistent_user_returns_none(self):
        self.assertIsNone(sc.get_user_centro("no_existe", self.db))


# ─────────────────────────────────────────────────────────────────────────────
# 16. truncate_sheet_name
# ─────────────────────────────────────────────────────────────────────────────

class TestTruncateSheetName(unittest.TestCase):

    def test_short_unchanged(self):
        self.assertEqual(sc.truncate_sheet_name("DIC1"), "DIC1")

    def test_long_truncated_to_31(self):
        result = sc.truncate_sheet_name("A" * 40)
        self.assertLessEqual(len(result), 31)

    def test_exactly_31_ok(self):
        self.assertLessEqual(len(sc.truncate_sheet_name("B" * 31)), 31)


# ─────────────────────────────────────────────────────────────────────────────
# 17. validate_dataframe
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateDataframe(unittest.TestCase):

    def test_valid_df(self):
        df = pd.DataFrame({"A": [1], "B": [2]})
        self.assertTrue(sc.validate_dataframe(df, ["A", "B"], "test"))

    def test_missing_column(self):
        df = pd.DataFrame({"A": [1]})
        self.assertFalse(sc.validate_dataframe(df, ["A", "B"], "test"))

    def test_empty_df(self):
        self.assertFalse(sc.validate_dataframe(pd.DataFrame(), ["A"], "test"))

    def test_none_df(self):
        self.assertFalse(sc.validate_dataframe(None, ["A"], "test"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
