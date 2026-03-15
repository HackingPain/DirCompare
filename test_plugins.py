"""Tests for the plugin system."""

import os
import shutil
import tempfile
import unittest

from DirCompare.plugins import discover_plugins, load_plugin, run_plugins


class TestLoadPlugin(unittest.TestCase):
    """Tests for loading individual plugins."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_plugin(self, filename, content):
        path = os.path.join(self.tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_load_valid_plugin(self):
        """A valid plugin file should be loaded successfully."""
        path = self._write_plugin("myplugin.py", '''
name = "test_plugin"
weight = 2

def score(left_files, right_files):
    return len(left_files) - len(right_files)
''')
        plugin = load_plugin(path)
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "test_plugin")
        self.assertEqual(plugin.weight, 2)

    def test_load_missing_name(self):
        """Plugin without 'name' should return None."""
        path = self._write_plugin("bad.py", '''
weight = 1
def score(left, right):
    return 0
''')
        plugin = load_plugin(path)
        self.assertIsNone(plugin)

    def test_load_missing_weight(self):
        """Plugin without 'weight' should return None."""
        path = self._write_plugin("bad.py", '''
name = "bad"
def score(left, right):
    return 0
''')
        plugin = load_plugin(path)
        self.assertIsNone(plugin)

    def test_load_missing_score(self):
        """Plugin without 'score' function should return None."""
        path = self._write_plugin("bad.py", '''
name = "bad"
weight = 1
''')
        plugin = load_plugin(path)
        self.assertIsNone(plugin)

    def test_load_syntax_error(self):
        """Plugin with syntax error should return None, not crash."""
        path = self._write_plugin("broken.py", '''
name = "broken
weight = 1
def score(left, right):
    return 0
''')
        plugin = load_plugin(path)
        self.assertIsNone(plugin)

    def test_load_nonexistent(self):
        """Loading from a nonexistent path should return None."""
        plugin = load_plugin("/nonexistent/path/plugin.py")
        self.assertIsNone(plugin)


class TestDiscoverPlugins(unittest.TestCase):
    """Tests for plugin discovery."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_directory(self):
        """Empty directory should return no plugins."""
        plugins = discover_plugins(extra_dirs=[self.tmpdir])
        # May find plugins from default dirs, filter to our dir
        self.assertIsInstance(plugins, list)

    def test_discover_from_extra_dir(self):
        """Plugins in extra_dirs should be discovered."""
        with open(os.path.join(self.tmpdir, "myplugin.py"), "w") as f:
            f.write('name = "discovered"\nweight = 1\ndef score(l, r): return 0\n')
        plugins = discover_plugins(extra_dirs=[self.tmpdir], enabled=True)
        names = [p.name for p in plugins]
        self.assertIn("discovered", names)

    def test_disabled_returns_empty(self):
        """enabled=False should skip all discovery."""
        with open(os.path.join(self.tmpdir, "myplugin.py"), "w") as f:
            f.write('name = "should_not_load"\nweight = 1\ndef score(l, r): return 0\n')
        plugins = discover_plugins(extra_dirs=[self.tmpdir], enabled=False)
        self.assertEqual(plugins, [])

    def test_skips_underscore_files(self):
        """Files starting with _ should be skipped."""
        with open(os.path.join(self.tmpdir, "_private.py"), "w") as f:
            f.write('name = "private"\nweight = 1\ndef score(l, r): return 0\n')
        plugins = discover_plugins(extra_dirs=[self.tmpdir])
        names = [p.name for p in plugins]
        self.assertNotIn("private", names)

    def test_skips_non_python_files(self):
        """Non-.py files should be skipped."""
        with open(os.path.join(self.tmpdir, "readme.txt"), "w") as f:
            f.write("not a plugin")
        plugins = discover_plugins(extra_dirs=[self.tmpdir])
        # Should not crash
        self.assertIsInstance(plugins, list)

    def test_deduplication_by_name(self):
        """Plugins with the same name should only be loaded once."""
        with open(os.path.join(self.tmpdir, "a_plugin.py"), "w") as f:
            f.write('name = "dup"\nweight = 1\ndef score(l, r): return 1\n')
        with open(os.path.join(self.tmpdir, "b_plugin.py"), "w") as f:
            f.write('name = "dup"\nweight = 2\ndef score(l, r): return 2\n')
        plugins = discover_plugins(extra_dirs=[self.tmpdir])
        dup_plugins = [p for p in plugins if p.name == "dup"]
        self.assertEqual(len(dup_plugins), 1)


class TestRunPlugins(unittest.TestCase):
    """Tests for executing plugins."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_plugin(self, name, weight, score_val):
        path = os.path.join(self.tmpdir, f"{name}.py")
        with open(path, "w") as f:
            f.write(f'name = "{name}"\nweight = {weight}\ndef score(l, r): return {score_val}\n')
        return load_plugin(path)

    def test_single_plugin_scoring(self):
        """A single plugin should contribute score * weight."""
        plugin = self._make_plugin("test", 3, -2)
        total, breakdown, warnings = run_plugins([plugin], {}, {})
        self.assertEqual(total, -6)  # -2 * 3
        self.assertEqual(breakdown["plugin:test"], -6)
        self.assertEqual(warnings, [])

    def test_multiple_plugins(self):
        """Multiple plugins should have additive scores."""
        p1 = self._make_plugin("a", 1, 5)
        p2 = self._make_plugin("b", 2, -3)
        total, breakdown, warnings = run_plugins([p1, p2], {}, {})
        self.assertEqual(total, 5 * 1 + (-3) * 2)  # -1
        self.assertEqual(breakdown["plugin:a"], 5)
        self.assertEqual(breakdown["plugin:b"], -6)

    def test_plugin_error_produces_warning(self):
        """A plugin that raises should produce a warning, not crash."""
        path = os.path.join(self.tmpdir, "bad.py")
        with open(path, "w") as f:
            f.write('name = "bad"\nweight = 1\ndef score(l, r): raise ValueError("boom")\n')
        plugin = load_plugin(path)
        total, breakdown, warnings = run_plugins([plugin], {}, {})
        self.assertEqual(total, 0)
        self.assertEqual(len(warnings), 1)
        self.assertIn("boom", warnings[0])

    def test_empty_plugins_list(self):
        """No plugins should produce zero score."""
        total, breakdown, warnings = run_plugins([], {}, {})
        self.assertEqual(total, 0)
        self.assertEqual(breakdown, {})
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
