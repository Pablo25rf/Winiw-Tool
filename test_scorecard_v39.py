"""
test_scorecard_v37.py - Suite de tests para Winiw Quality Scorecard v3.7+
Ejecutar: python -m unittest test_scorecard_v37 -v
No toca la BD de produccion - usa ficheros SQLite temporales.
"""

import unittest
import os
import sys
import sqlite3
import tempfile
import pandas as pd
import numpy as np

os.environ.setdefault("WINIW_ADMIN_USER", "test_admin")
os.environ.setdefault("WINIW_ADMIN_PASS", "Test_Pass_Seguro_2024!")

import amazon_scorecard_ultra_robust_v3_FINAL as sc


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_db():
    """BD SQLite temporal con esquema completo."""
    tmp = tempfile.mktemp(suffix='.db')
    db_config = {'type': 'sqlite', 'path': tmp}
    sc.init_database(db_config)
    conn = sqlite3.connect(tmp)
    return db_config, conn, tmp


def teardown_db(conn, tmp):
    try:
        conn.close()
        os.unlink(tmp)
    except Exception:
        pass


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
# 4. week_to_date  (devuelve fecha o fecha actual si no puede parsear)
# ─────────────────────────────────────────────────────────────────────────────

class TestWeekToDate(unittest.TestCase):

    def test_standard_week(self):
        self.assertIsNotNone(sc.week_to_date("W07"))

    def test_zero_padded_equals_unpadded(self):
        self.assertEqual(sc.week_to_date("W07"), sc.week_to_date("W7"))

    def test_week_01(self):
        self.assertIsNotNone(sc.week_to_date("W01"))

    def test_week_52(self):
        self.assertIsNotNone(sc.week_to_date("W52"))

    def test_returns_string_or_none(self):
        # El motor puede devolver fecha actual para input invalido - simplemente no crashea
        result = sc.week_to_date("INVALID")
        self.assertTrue(result is None or isinstance(result, str))


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

    def test_hash_is_stable(self):
        # Con o sin bcrypt, el mismo password siempre verifica correctamente
        h = sc.hash_password("test123")
        self.assertTrue(sc.verify_password("test123", h))

    def test_long_password(self):
        h = sc.hash_password("a" * 72)
        self.assertTrue(sc.verify_password("a" * 72, h))

    def test_special_chars(self):
        pw = "P@$$w0rd!#"
        h = sc.hash_password(pw)
        self.assertTrue(sc.verify_password(pw, h))

    @unittest.skipUnless(sc.HAS_BCRYPT, "bcrypt no instalado - hash determinista")
    def test_hash_unique_per_call(self):
        h1 = sc.hash_password("test123")
        h2 = sc.hash_password("test123")
        self.assertNotEqual(h1, h2)


# ─────────────────────────────────────────────────────────────────────────────
# 6. init_database
# ─────────────────────────────────────────────────────────────────────────────

class TestInitDatabase(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

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
        self.db, self.conn, self.tmp = make_db()
        self.conn.execute(
            "INSERT INTO users (username, password, role, active, must_change_password) "
            "VALUES ('jt_test', ?, 'jt', 1, 1)",
            (sc.hash_password("oldpass"),)
        )
        self.conn.commit()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

    def test_update_returns_truthy(self):
        result = sc.update_user_password("jt_test", sc.hash_password("newpass"), self.db)
        self.assertIsNotNone(result)

    def test_new_password_verifiable(self):
        new_hash = sc.hash_password("newpass")
        sc.update_user_password("jt_test", new_hash, self.db)
        # Re-open to get fresh connection
        conn2 = sqlite3.connect(self.tmp)
        row = conn2.execute("SELECT password FROM users WHERE username='jt_test'").fetchone()
        conn2.close()
        self.assertTrue(sc.verify_password("newpass", row[0]))

    def test_must_change_cleared(self):
        sc.update_user_password("jt_test", sc.hash_password("newpass"), self.db)
        conn2 = sqlite3.connect(self.tmp)
        row = conn2.execute("SELECT must_change_password FROM users WHERE username='jt_test'").fetchone()
        conn2.close()
        self.assertEqual(row[0], 0)


# ─────────────────────────────────────────────────────────────────────────────
# 8. rate limiting  (check_login_locked devuelve (bool, int))
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimiting(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

    def _is_locked(self, username):
        result = sc.check_login_locked(username, self.db)
        # Motor devuelve (bool, int) o bool segun version
        if isinstance(result, tuple):
            return result[0]
        return bool(result)

    def test_not_locked_initially(self):
        self.assertFalse(self._is_locked("nuevo_user"))

    def test_record_attempt_no_crash(self):
        try:
            sc.record_login_attempt("user1", False, self.db)
        except Exception as e:
            self.fail(f"record_login_attempt lanzo excepcion: {e}")

    def test_locked_after_max_failures(self):
        for _ in range(6):
            sc.record_login_attempt("brute", False, self.db)
        self.assertTrue(self._is_locked("brute"))

    def test_success_resets_lock(self):
        for _ in range(4):
            sc.record_login_attempt("user2", False, self.db)
        sc.record_login_attempt("user2", True, self.db)
        self.assertFalse(self._is_locked("user2"))


# ─────────────────────────────────────────────────────────────────────────────
# 9. get_center_targets / save_center_targets
# ─────────────────────────────────────────────────────────────────────────────

class TestCenterTargets(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

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
        sc.save_center_targets({**custom, "centro": "DIC1"}, self.db)
        loaded = sc.get_center_targets("DIC1", db_config=self.db)
        self.assertAlmostEqual(loaded.get("target_dnr", -1), 1.0)
        self.assertAlmostEqual(loaded.get("target_dcr", -1), 0.99)

    def test_different_centers_independent(self):
        sc.save_center_targets({"centro":"DIC1","target_dnr":0.5,"target_dcr":0.995,"target_pod":0.99,"target_cc":0.99,"target_fdps":0.98,"target_rts":0.01,"target_cdf":0.95}, self.db)
        sc.save_center_targets({"centro":"DIC2","target_dnr":2.0,"target_dcr":0.995,"target_pod":0.99,"target_cc":0.99,"target_fdps":0.98,"target_rts":0.01,"target_cdf":0.95}, self.db)
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
        _, _, score = sc.calculate_score_v3_robust(self._perfect(), self.TARGETS)
        self.assertGreaterEqual(score, 85)

    def test_terrible_score_poor(self):
        cal, _, _ = sc.calculate_score_v3_robust(self._terrible(), self.TARGETS)
        self.assertEqual(cal, "🛑 POOR")

    def test_score_within_range(self):
        for row in [self._perfect(), self._terrible()]:
            _, _, score = sc.calculate_score_v3_robust(row, self.TARGETS)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_returns_three_values(self):
        self.assertEqual(len(sc.calculate_score_v3_robust(self._perfect(), self.TARGETS)), 3)

    def test_dnr_penalizes(self):
        _, _, s_ok = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DNR": 0}), self.TARGETS)
        _, _, s_bad = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DNR": 8}), self.TARGETS)
        self.assertGreater(s_ok, s_bad)

    def test_fs_penalizes(self):
        _, _, s_ok = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "FS_Count": 0}), self.TARGETS)
        _, _, s_bad = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "FS_Count": 20}), self.TARGETS)
        self.assertGreater(s_ok, s_bad)

    def test_dcr_penalizes(self):
        _, _, s_ok = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DCR": 1.0}), self.TARGETS)
        _, _, s_bad = sc.calculate_score_v3_robust(
            pd.Series({**self._perfect(), "DCR": 0.90}), self.TARGETS)
        self.assertGreater(s_ok, s_bad)

    def test_calificacion_is_valid(self):
        valid = {"💎 FANTASTIC", "🥇 GREAT", "⚠️ FAIR", "🛑 POOR"}
        cal, _, _ = sc.calculate_score_v3_robust(self._perfect(), self.TARGETS)
        self.assertIn(cal, valid)
        cal2, _, _ = sc.calculate_score_v3_robust(self._terrible(), self.TARGETS)
        self.assertIn(cal2, valid)


# ─────────────────────────────────────────────────────────────────────────────
# 11. process_concessions
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessConcessions(unittest.TestCase):

    def _df(self, n=4):
        return pd.DataFrame({
            "Nombre del agente de entrega":           [f"Driver {i}" for i in range(n)],
            "ID de agente de entrega":                [f"AMZ{i:03d}" for i in range(n)],
            "Paquetes entregados no recibidos (DNR)": [i % 3 for i in range(n)],
            "Return to Station (RTS) - Porcentaje":   [f"{1+i*0.1:.1f}%" for i in range(n)],
            "Paquetes entregados":                    [100 + i*10 for i in range(n)],
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
            "Transporter ID":   ["AMZ001", "AMZ002", "AMZ003"],
            "False Scan Count": [0, 2, 5],
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
        self.assertIsInstance(sc.merge_data_smart(self._conc(), self._qual(), None, None, None, None), pd.DataFrame)

    def test_preserves_base_count(self):
        result = sc.merge_data_smart(self._conc(5), self._qual(5), None, None, None, None)
        self.assertEqual(len(result), 5)

    def test_quality_columns_merged(self):
        result = sc.merge_data_smart(self._conc(), self._qual(), None, None, None, None)
        self.assertIn("DCR", result.columns)

    def test_none_quality_handled(self):
        result = sc.merge_data_smart(self._conc(), None, None, None, None, None)
        self.assertEqual(len(result), 3)

    def test_all_optional_none(self):
        result = sc.merge_data_smart(self._conc(), None, None, None, None, None)
        self.assertIsInstance(result, pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# 15. get_user_centro / set_user_centro
# ─────────────────────────────────────────────────────────────────────────────

class TestUserCentro(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()
        self.conn.execute(
            "INSERT INTO users (username, password, role, active, must_change_password) "
            "VALUES ('jt_test', 'hash', 'jt', 1, 0)"
        )
        self.conn.commit()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

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
# 17. validate_dataframe  (devuelve (bool, str) - comprobamos [0])
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateDataframe(unittest.TestCase):

    def _ok(self, result):
        return result[0] if isinstance(result, tuple) else bool(result)

    def test_valid_df(self):
        df = pd.DataFrame({"A": [1], "B": [2]})
        self.assertTrue(self._ok(sc.validate_dataframe(df, ["A", "B"], "test")))

    def test_missing_column(self):
        df = pd.DataFrame({"A": [1]})
        self.assertFalse(self._ok(sc.validate_dataframe(df, ["A", "B"], "test")))

    def test_empty_df(self):
        self.assertFalse(self._ok(sc.validate_dataframe(pd.DataFrame(), ["A"], "test")))

    def test_none_df(self):
        self.assertFalse(self._ok(sc.validate_dataframe(None, ["A"], "test")))



# ─────────────────────────────────────────────────────────────────────────────
# 18. save_to_database / delete_scorecard_batch
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveToDatabase(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

    def _df(self, n=2):
        rows = []
        for i in range(n):
            rows.append({
                'ID': f'DA{i:03d}', 'Nombre': f'Driver {i}',
                'CALIFICACION': '🥇 GREAT', 'SCORE': 85.0,
                'Entregados': 100, 'DNR': 0, 'FS_Count': 0,
                'DNR_RISK_EVENTS': 0, 'DCR': 0.996, 'POD': 0.995,
                'CC': 0.995, 'FDPS': 0.99, 'RTS': 0.005, 'CDF': 0.97,
                'DETALLES': 'OK',
            })
        return pd.DataFrame(rows)

    def test_save_returns_true(self):
        self.assertTrue(sc.save_to_database(self._df(), 'W07', 'DIC1', self.db))

    def test_save_persists_rows(self):
        sc.save_to_database(self._df(3), 'W07', 'DIC1', self.db)
        cur = self.conn.execute("SELECT COUNT(*) FROM scorecards WHERE centro='DIC1' AND semana='W07'")
        self.assertEqual(cur.fetchone()[0], 3)

    def test_save_normalises_week(self):
        """W7 debe normalizarse a W07."""
        sc.save_to_database(self._df(1), 'W7', 'DIC1', self.db)
        cur = self.conn.execute("SELECT DISTINCT semana FROM scorecards WHERE centro='DIC1'")
        self.assertEqual(cur.fetchone()[0], 'W07')

    def test_save_clean_first_replaces(self):
        """Segunda llamada con clean_first=True reemplaza, no duplica."""
        sc.save_to_database(self._df(2), 'W07', 'DIC1', self.db)
        sc.save_to_database(self._df(2), 'W07', 'DIC1', self.db, clean_first=True)
        cur = self.conn.execute("SELECT COUNT(*) FROM scorecards WHERE centro='DIC1' AND semana='W07'")
        self.assertEqual(cur.fetchone()[0], 2)

    def test_save_empty_df_no_rows_inserted(self):
        """DataFrame vacio no inserta filas (aunque devuelva True)."""
        sc.save_to_database(pd.DataFrame(), 'W07', 'DIC1', self.db)
        cur = self.conn.execute("SELECT COUNT(*) FROM scorecards WHERE semana='W07'")
        self.assertEqual(cur.fetchone()[0], 0)

    def test_delete_batch_removes_rows(self):
        sc.save_to_database(self._df(2), 'W08', 'DIC1', self.db)
        sc.delete_scorecard_batch('W08', 'DIC1', self.db)
        cur = self.conn.execute("SELECT COUNT(*) FROM scorecards WHERE semana='W08'")
        self.assertEqual(cur.fetchone()[0], 0)

    def test_delete_nonexistent_batch_ok(self):
        """Borrar un lote que no existe no debe lanzar excepcion."""
        self.assertTrue(sc.delete_scorecard_batch('W99', 'ZZZ', self.db))


# ─────────────────────────────────────────────────────────────────────────────
# 19. save_station_scorecard / get_station_scorecards
# ─────────────────────────────────────────────────────────────────────────────


    # ─── v3.9: columna anio + driver_name en scorecards ────────────────

    def test_guarda_3_drivers(self, db_con_datos):
        conn = sqlite3.connect(db_con_datos['path'])
        count = conn.execute(
            "SELECT COUNT(*) FROM scorecards WHERE semana='W07' AND centro='DMA3'"
        ).fetchone()[0]
        conn.close()
        assert count == 3
    def test_anio_relleno(self, db_con_datos):
        """La columna anio se rellena automáticamente con el año de la semana."""
        conn = sqlite3.connect(db_con_datos['path'])
        rows = conn.execute(
            "SELECT DISTINCT anio FROM scorecards WHERE semana='W07' AND centro='DMA3'"
        ).fetchall()
        conn.close()
        anios = [r[0] for r in rows]
        assert len(anios) == 1
        assert anios[0] == 2026  # week_to_date('W07') → 2026
    def test_driver_name_guardado(self, db_con_datos):
        conn = sqlite3.connect(db_con_datos['path'])
        nombre = conn.execute(
            "SELECT driver_name FROM scorecards WHERE driver_id='A2ZZWVAGH7MFN4'"
        ).fetchone()[0]
        conn.close()
        assert nombre == 'Juan García'
    def test_calificacion_fantastic(self, db_con_datos):
        conn = sqlite3.connect(db_con_datos['path'])
        cal = conn.execute(
            "SELECT calificacion FROM scorecards WHERE driver_id='A2ZZWVAGH7MFN4'"
        ).fetchone()[0]
        conn.close()
        assert cal == '💎 FANTASTIC'


# ─── 3. parse_dsp_scorecard_pdf ───────────────────────────────────────────────

PDF_PATH = os.path.join(
    os.path.dirname(__file__),
    'ES-TDSL-DMA3-Week7-DSP-Scorecard-3_0__3_.pdf'
)
PDF_AVAILABLE = os.path.exists(PDF_PATH)

# Intentar ruta alternativa (uploads)
if not PDF_AVAILABLE:
    _alt = '/mnt/user-data/uploads/ES-TDSL-DMA3-Week7-DSP-Scorecard-3_0__3_.pdf'
    if os.path.exists(_alt):
        PDF_PATH = _alt
        PDF_AVAILABLE = True

@pytest.mark.skipif(not PDF_AVAILABLE, reason="PDF de test no disponible")

class TestStationScorecard(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

    def _station(self, score=88, standing='GREAT'):
        return {
            'overall_score': score, 'overall_standing': standing,
            'rank_station': 3, 'rank_wow': -1,
            'whc_pct': 95.0, 'whc_tier': 'Great',
            'dcr_pct': 99.6, 'dcr_tier': 'Fantastic',
            'dnr_dpmo': 120, 'dnr_tier': 'Great',
            'lor_dpmo': 80, 'lor_tier': 'Fantastic',
            'fico': 92, 'fico_tier': 'Fantastic',
            'pod_pct': 99.2, 'pod_tier': 'Great',
            'focus_area_1': 'DNR', 'focus_area_2': 'DCR', 'focus_area_3': None,
        }

    def test_save_returns_true(self):
        self.assertTrue(sc.save_station_scorecard(self._station(), 'W07', 'DIC1', self.db))

    def test_get_returns_dataframe(self):
        sc.save_station_scorecard(self._station(), 'W07', 'DIC1', self.db)
        df = sc.get_station_scorecards(self.db)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)

    def test_get_contains_correct_score(self):
        sc.save_station_scorecard(self._station(score=92, standing='FANTASTIC'), 'W07', 'DIC1', self.db)
        df = sc.get_station_scorecards(self.db)
        self.assertEqual(df.iloc[0]['overall_score'], 92)

    def test_get_empty_db_returns_empty_df(self):
        df = sc.get_station_scorecards(self.db)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 0)

    def test_upsert_same_week_replaces(self):
        """Guardar dos veces la misma semana/centro debe actualizar, no duplicar."""
        sc.save_station_scorecard(self._station(score=80), 'W07', 'DIC1', self.db)
        sc.save_station_scorecard(self._station(score=90), 'W07', 'DIC1', self.db)
        df = sc.get_station_scorecards(self.db)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['overall_score'], 90)


# ─────────────────────────────────────────────────────────────────────────────
# 20. save_wh_exceptions / update_drivers_from_pdf
# ─────────────────────────────────────────────────────────────────────────────

class TestPdfDataFunctions(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

    def test_save_wh_empty_ok(self):
        df = pd.DataFrame(columns=['driver_id', 'driver_name', 'hours_worked', 'threshold'])
        self.assertTrue(sc.save_wh_exceptions(df, 'W07', 'DIC1', self.db))

    def test_update_drivers_empty_df(self):
        n_upd, n_miss = sc.update_drivers_from_pdf(pd.DataFrame(), 'W07', 'DIC1', self.db)
        self.assertEqual(n_upd, 0)
        self.assertEqual(n_miss, 0)

    def test_update_drivers_no_match(self):
        """Si no hay conductores en BD, todos son n_miss."""
        drivers = pd.DataFrame([{'driver_id': 'DA999', 'driver_name': 'Ghost Driver',
                                  'dcr_pdf': 0.996, 'pod_pdf': 0.99}])
        n_upd, n_miss = sc.update_drivers_from_pdf(drivers, 'W07', 'DIC1', self.db)
        self.assertEqual(n_upd, 0)
        self.assertEqual(n_miss, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 21. clean_database_duplicates / run_maintenance
# ─────────────────────────────────────────────────────────────────────────────

class TestMaintenance(unittest.TestCase):

    def setUp(self):
        self.db, self.conn, self.tmp = make_db()

    def tearDown(self):
        teardown_db(self.conn, self.tmp)

    def test_clean_duplicates_empty_db(self):
        ok, n = sc.clean_database_duplicates(self.db)
        self.assertTrue(ok)
        self.assertEqual(n, 0)

    def test_run_maintenance_empty_db(self):
        ok, n = sc.run_maintenance(self.db)
        self.assertTrue(ok)
        self.assertGreaterEqual(n, 0)

    def test_run_maintenance_returns_tuple(self):
        result = sc.run_maintenance(self.db)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


# ─────────────────────────────────────────────────────────────────────────────
# 22. parse_dsp_scorecard_pdf — sin PDF real (fallback sin pdfplumber)
# ─────────────────────────────────────────────────────────────────────────────

class TestParseDspScorecardPdf(unittest.TestCase):

    def test_invalid_bytes_returns_not_ok(self):
        """Bytes aleatorios devuelven ok=False sin lanzar excepcion."""
        result = sc.parse_dsp_scorecard_pdf(b"not a pdf")
        self.assertIsInstance(result, dict)
        self.assertIn('ok', result)
        self.assertIn('errors', result)
        self.assertIn('meta', result)
        self.assertIn('station', result)
        self.assertIn('drivers', result)
        self.assertIn('wh', result)

    def test_empty_bytes_returns_not_ok(self):
        result = sc.parse_dsp_scorecard_pdf(b"")
        self.assertFalse(result['ok'])

    def test_drivers_is_dataframe(self):
        result = sc.parse_dsp_scorecard_pdf(b"not a pdf")
        self.assertIsInstance(result['drivers'], pd.DataFrame)

    def test_wh_is_dataframe(self):
        result = sc.parse_dsp_scorecard_pdf(b"not a pdf")
        self.assertIsInstance(result['wh'], pd.DataFrame)

    def test_errors_is_list(self):
        result = sc.parse_dsp_scorecard_pdf(b"not a pdf")
        self.assertIsInstance(result['errors'], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ═══ Fixtures v3.9 (necesarios para las nuevas clases) ═══════════════════════

@pytest.fixture
def db(tmp_path):
    """BD SQLite limpia para cada test."""
    db_file = str(tmp_path / "test.db")
    cfg = {'type': 'sqlite', 'path': db_file}
    m.init_database(cfg)
    return cfg

@pytest.fixture
def db_con_datos(db):
    """BD con 3 conductores ya insertados en scorecards."""
    df = pd.DataFrame([
        {'ID': 'A2ZZWVAGH7MFN4', 'Nombre': 'Juan García',
         'CALIFICACION': '💎 FANTASTIC', 'SCORE': 92.0,
         'Entregados': 310, 'DNR': 0.5, 'FS_Count': 0,
         'DNR_RISK_EVENTS': 0, 'DCR': 0.99, 'POD': 0.98,
         'CC': 0.97, 'FDPS': 0.99, 'RTS': 0.01, 'CDF': 0.95,
         'DETALLES': ''},
        {'ID': 'A9XGFDJ3UDX1D', 'Nombre': 'María López',
         'CALIFICACION': '🥇 GREAT', 'SCORE': 84.0,
         'Entregados': 280, 'DNR': 1.2, 'FS_Count': 0,
         'DNR_RISK_EVENTS': 0, 'DCR': 0.975, 'POD': 0.96,
         'CC': 0.95, 'FDPS': 0.98, 'RTS': 0.01, 'CDF': 0.94,
         'DETALLES': ''},
        {'ID': 'A3ITJEWLL658FO', 'Nombre': 'Pedro Ruiz',
         'CALIFICACION': '⚠️ FAIR', 'SCORE': 68.0,
         'Entregados': 190, 'DNR': 3.5, 'FS_Count': 1,
         'DNR_RISK_EVENTS': 2, 'DCR': 0.96, 'POD': 0.93,
         'CC': 0.91, 'FDPS': 0.97, 'RTS': 0.02, 'CDF': 0.90,
         'DETALLES': 'DNR alto'},
    ])
    m.save_to_database(df, 'W07', 'DMA3', db, uploaded_by='test')
    return db


# ─── 1. Schema e init_database ────────────────────────────────────────────────



# ═══════════════════════════════════════════════════════════════════════════
# TESTS v3.9 — Nuevas funcionalidades
# ═══════════════════════════════════════════════════════════════════════════


class TestSchema:

    def test_tablas_creadas(self, db):
        """Todas las tablas esenciales existen."""
        with m.db_connection(db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas = {r[0] for r in cursor.fetchall()}
        assert 'scorecards'         in tablas
        assert 'station_scorecards' in tablas
        assert 'wh_exceptions'      in tablas
        assert 'center_targets'     in tablas
        assert 'users'              in tablas
        assert 'login_attempts'     in tablas

    def test_scorecards_columnas(self, db):
        """scorecards tiene todas las columnas esperadas incluyendo anio."""
        with m.db_connection(db) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(scorecards)")
            cols = {r[1] for r in cursor.fetchall()}
        esperadas = {
            'id', 'semana', 'fecha_semana', 'anio', 'centro',
            'driver_id', 'driver_name', 'calificacion', 'score',
            'entregados', 'dnr', 'dcr', 'pod', 'cc', 'fdps', 'rts', 'cdf',
            'entregados_oficial', 'dcr_oficial', 'pod_oficial', 'cc_oficial',
            'dsc_dpmo', 'lor_dpmo', 'ce_dpmo', 'cdf_dpmo_oficial', 'pdf_loaded',
            'uploaded_by', 'timestamp',
        }
        missing = esperadas - cols
        assert not missing, f"Columnas faltantes en scorecards: {missing}"

    def test_wh_exceptions_columnas(self, db):
        """wh_exceptions tiene driver_name y anio."""
        with m.db_connection(db) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(wh_exceptions)")
            cols = {r[1] for r in cursor.fetchall()}
        assert 'driver_name'           in cols
        assert 'anio'                  in cols
        assert 'driver_id'             in cols
        assert 'daily_limit_exceeded'  in cols
        assert 'weekly_limit_exceeded' in cols
        assert 'under_offwork_limit'   in cols
        assert 'workday_limit_exceeded' in cols

    def test_unique_constraint_scorecards(self, db_con_datos):
        """No se pueden insertar dos filas con mismo semana+centro+driver_id."""
        df2 = pd.DataFrame([{
            'ID': 'A2ZZWVAGH7MFN4', 'Nombre': 'Juan García Duplicado',
            'CALIFICACION': '🥇 GREAT', 'SCORE': 80.0,
            'Entregados': 300, 'DNR': 0.8, 'FS_Count': 0,
            'DNR_RISK_EVENTS': 0, 'DCR': 0.98, 'POD': 0.97,
            'CC': 0.96, 'FDPS': 0.98, 'RTS': 0.01, 'CDF': 0.94,
            'DETALLES': '',
        }])
        # Debe hacer upsert, no duplicar
        m.save_to_database(df2, 'W07', 'DMA3', db_con_datos, uploaded_by='test')
        conn = sqlite3.connect(db_con_datos['path'])
        count = conn.execute(
            "SELECT COUNT(*) FROM scorecards WHERE semana='W07' AND centro='DMA3'"
        ).fetchone()[0]
        conn.close()
        assert count == 3  # sigue siendo 3, no 4


# ─── 2. save_to_database + columna anio ──────────────────────────────────────


class TestParseDspPdf:

    @pytest.fixture(scope='class')
    def parsed(self):
        pdf_bytes = open(PDF_PATH, 'rb').read()
        return m.parse_dsp_scorecard_pdf(pdf_bytes)

    def test_ok(self, parsed):
        assert parsed['ok'] is True

    def test_meta_centro(self, parsed):
        assert parsed['meta']['centro'] == 'DMA3'

    def test_meta_semana(self, parsed):
        assert parsed['meta']['semana'] == 'W07'

    def test_meta_year(self, parsed):
        assert parsed['meta']['year'] == 2026

    def test_overall_score(self, parsed):
        assert parsed['station']['overall_score'] == 81.11

    def test_overall_standing(self, parsed):
        assert parsed['station']['overall_standing'] == 'Great'

    def test_rank_station(self, parsed):
        assert parsed['station']['rank_station'] == 3

    def test_rank_wow(self, parsed):
        """BUG CORREGIDO: rank_wow no era None con espacio antes del número."""
        assert parsed['station']['rank_wow'] == 3

    def test_whc_pct(self, parsed):
        assert parsed['station']['whc_pct'] == 85.87

    def test_whc_tier(self, parsed):
        assert parsed['station']['whc_tier'] == 'Poor'

    def test_dcr_pct(self, parsed):
        assert parsed['station']['dcr_pct'] == 97.47

    def test_fico(self, parsed):
        assert parsed['station']['fico'] == 841.0

    def test_drivers_count(self, parsed):
        """BUG CORREGIDO: drivers desde páginas [2,3] — NO incluye página WHC."""
        assert len(parsed['drivers']) == 93

    def test_drivers_primer_id(self, parsed):
        assert parsed['drivers'].iloc[0]['driver_id'] == 'A102GVKIDVMZ4O'

    def test_drivers_columnas(self, parsed):
        cols = set(parsed['drivers'].columns)
        for c in ('driver_id', 'entregados_oficial', 'dcr_oficial',
                  'pod_oficial', 'cc_oficial', 'cdf_dpmo_oficial'):
            assert c in cols, f"Columna faltante en drivers: {c}"

    def test_wh_count(self, parsed):
        """BUG CORREGIDO: WHC desde página índice 4, no 5 (SLS targets)."""
        assert len(parsed['wh']) == 13

    def test_wh_primer_driver(self, parsed):
        assert parsed['wh'].iloc[0]['driver_id'] == 'A2ZZWVAGH7MFN4'

    def test_sin_errores_fatales(self, parsed):
        assert parsed['errors'] == [], f"Errores: {parsed['errors']}"


# ─── 4. save_wh_exceptions con driver_name y anio ────────────────────────────


class TestSaveWhExceptions:

    def _get_wh_df(self):
        return pd.DataFrame([
            {'driver_id': 'A2ZZWVAGH7MFN4',
             'daily_limit_exceeded': 0, 'weekly_limit_exceeded': 0,
             'under_offwork_limit': 1, 'workday_limit_exceeded': 0},
            {'driver_id': 'A9XGFDJ3UDX1D',
             'daily_limit_exceeded': 0, 'weekly_limit_exceeded': 1,
             'under_offwork_limit': 0, 'workday_limit_exceeded': 0},
            {'driver_id': 'AXXX_SIN_CSV',     # no está en scorecards
             'daily_limit_exceeded': 1, 'weekly_limit_exceeded': 0,
             'under_offwork_limit': 0, 'workday_limit_exceeded': 1},
        ])

    def test_retorna_true(self, db_con_datos):
        result = m.save_wh_exceptions(
            self._get_wh_df(), 'W07', 'DMA3', db_con_datos, 'tester'
        )
        assert result is True

    def test_guarda_3_filas(self, db_con_datos):
        m.save_wh_exceptions(self._get_wh_df(), 'W07', 'DMA3', db_con_datos)
        conn = sqlite3.connect(db_con_datos['path'])
        count = conn.execute(
            "SELECT COUNT(*) FROM wh_exceptions WHERE semana='W07' AND centro='DMA3'"
        ).fetchone()[0]
        conn.close()
        assert count == 3

    def test_driver_name_lookup_ok(self, db_con_datos):
        """Drivers con CSV tienen nombre; el que no tiene CSV queda NULL."""
        m.save_wh_exceptions(self._get_wh_df(), 'W07', 'DMA3', db_con_datos)
        conn = sqlite3.connect(db_con_datos['path'])
        rows = {r[0]: r[1] for r in conn.execute(
            "SELECT driver_id, driver_name FROM wh_exceptions "
            "WHERE semana='W07' AND centro='DMA3'"
        ).fetchall()}
        conn.close()
        assert rows['A2ZZWVAGH7MFN4'] == 'Juan García'
        assert rows['A9XGFDJ3UDX1D']  == 'María López'
        assert rows['AXXX_SIN_CSV']    is None   # sin CSV → NULL

    def test_anio_relleno(self, db_con_datos):
        """La columna anio se rellena en wh_exceptions."""
        m.save_wh_exceptions(self._get_wh_df(), 'W07', 'DMA3', db_con_datos)
        conn = sqlite3.connect(db_con_datos['path'])
        anios = [r[0] for r in conn.execute(
            "SELECT DISTINCT anio FROM wh_exceptions WHERE semana='W07'"
        ).fetchall()]
        conn.close()
        assert anios == [2026]

    def test_idempotente(self, db_con_datos):
        """Guardar dos veces el mismo centro+semana no duplica filas."""
        m.save_wh_exceptions(self._get_wh_df(), 'W07', 'DMA3', db_con_datos)
        m.save_wh_exceptions(self._get_wh_df(), 'W07', 'DMA3', db_con_datos)
        conn = sqlite3.connect(db_con_datos['path'])
        count = conn.execute(
            "SELECT COUNT(*) FROM wh_exceptions WHERE semana='W07' AND centro='DMA3'"
        ).fetchone()[0]
        conn.close()
        assert count == 3

    def test_vacio_no_falla(self, db):
        """DataFrame vacío no lanza excepción."""
        result = m.save_wh_exceptions(pd.DataFrame(), 'W07', 'DMA3', db)
        assert result is True

    def test_none_no_falla(self, db):
        """None no lanza excepción."""
        result = m.save_wh_exceptions(None, 'W07', 'DMA3', db)
        assert result is True


# ─── 5. get_station_scorecards con wh_count ───────────────────────────────────


class TestGetStationScorecards:

    def _insertar_station(self, db):
        """Inserta un station_scorecard mínimo."""
        with m.db_connection(db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO station_scorecards
                    (semana, centro, overall_score, overall_standing, rank_station)
                VALUES ('W07', 'DMA3', 81.11, 'Great', 3)
            """)
            conn.commit()

    def test_sin_datos_devuelve_df_vacio(self, db):
        df = m.get_station_scorecards(db)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_wh_count_cero_sin_excepciones(self, db):
        """wh_count=0 cuando no hay wh_exceptions para ese centro/semana."""
        self._insertar_station(db)
        df = m.get_station_scorecards(db)
        assert 'wh_count' in df.columns
        assert int(df.iloc[0]['wh_count']) == 0

    def test_wh_count_con_excepciones(self, db_con_datos):
        """wh_count refleja el número real de excepciones guardadas."""
        self._insertar_station(db_con_datos)
        wh_df = pd.DataFrame([
            {'driver_id': 'A2ZZWVAGH7MFN4',
             'daily_limit_exceeded': 0, 'weekly_limit_exceeded': 1,
             'under_offwork_limit': 0, 'workday_limit_exceeded': 0},
            {'driver_id': 'A9XGFDJ3UDX1D',
             'daily_limit_exceeded': 1, 'weekly_limit_exceeded': 0,
             'under_offwork_limit': 0, 'workday_limit_exceeded': 0},
        ])
        m.save_wh_exceptions(wh_df, 'W07', 'DMA3', db_con_datos)
        df = m.get_station_scorecards(db_con_datos)
        row = df[df['centro'] == 'DMA3'].iloc[0]
        assert int(row['wh_count']) == 2

    def test_wh_count_columna_existe(self, db):
        """La columna wh_count siempre aparece aunque no haya datos."""
        self._insertar_station(db)
        df = m.get_station_scorecards(db)
        assert 'wh_count' in df.columns


# ─── 6. Funciones de utilidad ─────────────────────────────────────────────────


class TestRegresiones:

    def test_paginas_drivers_no_incluye_whc(self):
        """
        BUG CORREGIDO v3.9: parse_dsp_scorecard_pdf usaba [2,3,4]
        incluyendo la página WHC en los drivers.
        Verificamos que el código usa [2, 3].
        """
        import inspect
        src = inspect.getsource(m.parse_dsp_scorecard_pdf)
        assert 'for page_idx in [2, 3]:' in src, \
            "drivers debe iterar [2,3] NO [2,3,4]"
        assert 'for page_idx in [2, 3, 4]:' not in src, \
            "No debe iterar [2,3,4] (incluye página WHC)"

    def test_pagina_whc_es_indice_4(self):
        """
        BUG CORREGIDO v3.9: WHC estaba en páginas[5] (SLS targets).
        Ahora debe usar páginas[4].
        """
        import inspect
        src = inspect.getsource(m.parse_dsp_scorecard_pdf)
        # La sección WHC debe usar índice 4
        wh_section = src[src.find('# ── PÁGINA 5: Working Hours'):]
        assert 'pdf.pages[4].extract_table()' in wh_section[:300], \
            "WHC debe leer páginas[4]"

    def test_wh_exceptions_tiene_driver_name_schema(self):
        """
        BUG CORREGIDO v3.9: wh_exceptions no tenía driver_name.
        Verificamos que el CREATE TABLE lo incluye.
        """
        import inspect
        src = inspect.getsource(m.init_database)
        wh_block = src[src.find('CREATE TABLE IF NOT EXISTS wh_exceptions'):]
        wh_block = wh_block[:wh_block.find('UNIQUE(semana, centro, driver_id)')]
        assert 'driver_name' in wh_block, \
            "CREATE TABLE wh_exceptions debe incluir driver_name"

    def test_save_wh_hace_lookup_nombre(self):
        """
        BUG CORREGIDO v3.9: save_wh_exceptions no buscaba driver_name.
        Verificamos que el código tiene el SELECT de lookup.
        """
        import inspect
        src = inspect.getsource(m.save_wh_exceptions)
        assert 'SELECT driver_id, driver_name FROM scorecards' in src, \
            "save_wh_exceptions debe hacer lookup de driver_name"
        assert 'name_map' in src

    def test_scorecards_tiene_anio(self):
        """
        NUEVO v3.9: columna anio para Power BI.
        """
        import inspect
        src = inspect.getsource(m.init_database)
        # Verificar migración
        assert 'anio' in src

    def test_insert_scorecards_incluye_anio(self):
        """
        NUEVO v3.9: save_to_database debe incluir anio en el INSERT.
        """
        import inspect
        src = inspect.getsource(m.save_to_database)
        assert '"anio"' in src, "cols de scorecards debe incluir 'anio'"
        assert 'year_int' in src, "Debe calcular year_int para insertar"

    def test_get_station_scorecards_incluye_wh_count(self):
        """
        NUEVO v3.9: get_station_scorecards debe devolver wh_count
        via LEFT JOIN con wh_exceptions.
        """
        import inspect
        src = inspect.getsource(m.get_station_scorecards)
        assert 'wh_count' in src
        assert 'LEFT JOIN' in src
        assert 'wh_exceptions' in src


# ─── 8. Login y seguridad ────────────────────────────────────────────────────

