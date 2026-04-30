# src/Synaptipy/application/gui/help_window.py
# -*- coding: utf-8 -*-
"""
Offline Help viewer for Synaptipy.

Provides :class:`HelpWindow`, a standalone desktop window that displays the
bundled documentation without requiring an internet connection.

Three-tier resolution strategy
-------------------------------
1. **QHelpEngine** (`.qhc` / `.qch` artefacts) - full Contents/Index/Search
   navigation.  Available when :func:`build_offline_help.py` has been run,
   i.e. always in the PyInstaller bundle and in development after running the
   build script.

2. **Local HTML fallback** - ``QTextBrowser`` loading the Sphinx-built HTML
   tree.  Triggered when no ``.qhc`` is found but an ``index.html`` exists in
   one of the standard locations (e.g. plain ``pip install`` with HTML docs
   bundled in the wheel, or a dev checkout after ``make html``).

3. **Graceful message** - shown only when neither artefact type is present,
   with instructions for building them and a link to the online docs.

Path resolution order
----------------------
For each tier the search order is:

* ``sys._MEIPASS/...`` - PyInstaller frozen bundle.
* ``<package_root>/resources/docs/...`` - installed package (site-packages) or
  editable install.  ``<package_root>`` is
  ``Path(__file__).resolve().parents[2]`` which equals
  ``src/Synaptipy/`` for an editable install and
  ``<site-packages>/Synaptipy/`` for a regular install.
* ``<repo_root>/docs/_build/...`` - development checkout after running
  ``make html`` / ``make qthelp``.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtHelp, QtWidgets

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource path resolution
# ---------------------------------------------------------------------------

# Relative to sys._MEIPASS root
_QHC_MEIPASS = Path("Synaptipy") / "resources" / "docs" / "synaptipy.qhc"
_HTML_MEIPASS = Path("Synaptipy") / "resources" / "docs" / "html"


def _pkg_root() -> Path:
    """Return the package root directory.

    * Editable install: ``src/Synaptipy/``
    * Regular install:  ``<site-packages>/Synaptipy/``

    ``help_window.py`` lives two levels below the package root::

        <pkg_root>/application/gui/help_window.py
    """
    return Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    """Return the repository root (only meaningful in a source checkout).

    ``help_window.py`` lives four levels below the repo root::

        <repo_root>/src/Synaptipy/application/gui/help_window.py
    """
    return Path(__file__).resolve().parents[4]


def resolve_qhc_path() -> Optional[Path]:
    """Return the absolute path to ``synaptipy.qhc``, or *None* if not found.

    Search order:

    1. ``sys._MEIPASS`` (PyInstaller frozen bundle).
    2. ``<package_root>/resources/docs/synaptipy.qhc`` (pip install or editable
       install after running ``build_offline_help.py``).
    3. ``<repo_root>/docs/_build/qthelp/synaptipy.qhc`` (development checkout
       after ``make qthelp``).
    """
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / _QHC_MEIPASS
        if candidate.exists():
            return candidate

    candidate = _pkg_root() / "resources" / "docs" / "synaptipy.qhc"
    if candidate.exists():
        return candidate

    candidate = _repo_root() / "docs" / "_build" / "qthelp" / "synaptipy.qhc"
    if candidate.exists():
        return candidate

    return None


def resolve_html_path() -> Optional[Path]:
    """Return the directory containing offline HTML docs, or *None* if absent.

    Search order:

    1. ``sys._MEIPASS/.../docs/html/`` (PyInstaller frozen bundle).
    2. ``<package_root>/resources/docs/html/`` (pip install or editable
       install after running ``build_offline_help.py``).
    3. ``<repo_root>/docs/_build/html/`` (development checkout after
       ``make html``).
    """
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / _HTML_MEIPASS
        if (candidate / "index.html").exists():
            return candidate

    candidate = _pkg_root() / "resources" / "docs" / "html"
    if (candidate / "index.html").exists():
        return candidate

    candidate = _repo_root() / "docs" / "_build" / "html"
    if (candidate / "index.html").exists():
        return candidate

    return None


# ---------------------------------------------------------------------------
# QTextBrowser subclass for qthelp:// URLs (tier 1)
# ---------------------------------------------------------------------------


class _HelpBrowser(QtWidgets.QTextBrowser):
    """``QTextBrowser`` subclass that can render ``qthelp://`` URLs.

    ``QHelpEngine`` serves page content via ``fileData(QUrl)``.  Standard
    ``QTextBrowser`` only handles ``file://`` and ``qrc://``; we override
    ``loadResource`` so that any request for a ``qthelp://`` resource is
    satisfied by the engine instead.
    """

    def __init__(self, help_engine: QtHelp.QHelpEngine, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._engine = help_engine
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._navigate)

    def loadResource(self, resource_type: int, url: QtCore.QUrl) -> object:  # noqa: N802
        """Intercept ``qthelp://`` requests and serve them from the engine."""
        if url.scheme() == "qthelp":
            data = self._engine.fileData(url)
            if data:
                return data
        return super().loadResource(resource_type, url)

    def _navigate(self, url: QtCore.QUrl) -> None:
        """Handle link clicks inside the browser pane."""
        if url.scheme() in ("http", "https"):
            QtGui.QDesktopServices.openUrl(url)
        else:
            self.setSource(url)


# ---------------------------------------------------------------------------
# QTextBrowser subclass for local HTML file:// tree (tier 2)
# ---------------------------------------------------------------------------


class _LocalHtmlBrowser(QtWidgets.QTextBrowser):
    """``QTextBrowser`` that serves a local Sphinx HTML tree.

    Configuring ``searchPaths`` lets Qt resolve relative URLs (images, CSS)
    relative to the HTML root directory.  External links are delegated to the
    system browser so the user is never silently dropped into an unusable page.
    """

    def __init__(self, html_root: Path, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._home = QtCore.QUrl.fromLocalFile(str(html_root / "index.html"))
        # Add root so relative paths resolve correctly
        self.setSearchPaths([str(html_root)])
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._navigate)

    def go_home(self) -> None:
        """Navigate to the documentation index page."""
        self.setSource(self._home)

    def _navigate(self, url: QtCore.QUrl) -> None:
        """Delegate external URLs to the system browser; load local ones inline."""
        if url.scheme() in ("http", "https"):
            QtGui.QDesktopServices.openUrl(url)
        else:
            self.setSource(url)


# ---------------------------------------------------------------------------
# Main Help Window
# ---------------------------------------------------------------------------


class HelpWindow(QtWidgets.QMainWindow):
    """Standalone offline documentation viewer.

    Tries three rendering strategies in order:

    1. Full ``QHelpEngine`` viewer (Contents / Index / Search tabs + browser).
    2. Local HTML viewer using ``QTextBrowser`` with back/forward/home toolbar.
    3. Informational fallback message with build instructions.

    Instantiation never raises; the window always shows *something*.

    Args:
        parent: Optional parent widget.  Pass *None* (default) for a
                top-level window.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Synaptipy - Offline Documentation")
        self.resize(1100, 700)

        # --- Tier 1: QHelpEngine ---
        qhc_path = resolve_qhc_path()
        if qhc_path is not None:
            engine = QtHelp.QHelpEngine(str(qhc_path), self)
            if engine.setupData():
                self._engine = engine
                self._build_help_ui()
                return
            log.warning("QHelpEngine.setupData() failed for %s: %s", qhc_path, engine.error())

        # --- Tier 2: local HTML ---
        html_path = resolve_html_path()
        if html_path is not None:
            self._build_html_viewer_ui(html_path)
            return

        # --- Tier 3: graceful message ---
        self._build_no_docs_ui()

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------

    def _build_help_ui(self) -> None:
        """Construct the full QHelpEngine two-pane viewer (tier 1).

        Left pane layout::

            ┌──────────────────────┐
            │  QTabWidget          │  Contents / Index / Search
            │  (stretch = 1)       │
            ├──────────────────────┤
            │  QLabel (online link)│  fixed height; opens system browser
            └──────────────────────┘
        """
        self._browser = _HelpBrowser(self._engine, self)
        self._browser.setMinimumWidth(400)

        nav_tabs = QtWidgets.QTabWidget()
        nav_tabs.addTab(self._engine.contentWidget(), "Contents")
        nav_tabs.addTab(self._engine.indexWidget(), "Index")
        nav_tabs.addTab(self._build_search_tab(), "Search")

        # Online documentation link pinned to the bottom of the left pane.
        # setOpenExternalLinks(True) delegates the click to the OS browser
        # via QDesktopServices — no custom slot required.
        online_link = QtWidgets.QLabel(
            '<a href="https://synaptipy.readthedocs.io/en/latest/">' "View Online Documentation</a>"
        )
        online_link.setOpenExternalLinks(True)
        online_link.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        online_link.setContentsMargins(6, 4, 6, 6)
        online_link.setToolTip("Open the online documentation in your web browser")

        left_pane = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(nav_tabs)
        left_layout.addWidget(online_link)

        left_pane.setMinimumWidth(240)
        left_pane.setMaximumWidth(380)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(left_pane)
        splitter.addWidget(self._browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 820])
        self.setCentralWidget(splitter)

        self._engine.contentWidget().linkActivated.connect(self._browser.setSource)
        self._engine.indexWidget().linkActivated.connect(self._on_index_activated)
        self._open_home_page()

    def _build_search_tab(self) -> QtWidgets.QWidget:
        """Return the QHelpEngine full-text search widget."""
        search_engine = self._engine.searchEngine()
        search_engine.reindexDocumentation()

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        query_widget = search_engine.queryWidget()
        layout.addWidget(query_widget)
        result_widget = search_engine.resultWidget()
        layout.addWidget(result_widget)

        query_widget.search.connect(lambda: search_engine.search(query_widget.searchInput()))
        result_widget.requestShowLink.connect(self._browser.setSource)
        return container

    def _build_html_viewer_ui(self, html_root: Path) -> None:
        """Construct a simple HTML browser with navigation toolbar (tier 2).

        ``QTextBrowser`` renders Sphinx HTML acceptably without JavaScript.
        A lightweight toolbar provides back / forward / home navigation and
        displays the current page title.
        """
        browser = _LocalHtmlBrowser(html_root, self)

        # --- Toolbar ---
        toolbar = self.addToolBar("Navigation")
        toolbar.setMovable(False)

        back_action = toolbar.addAction("\u25c0  Back")
        back_action.setToolTip("Go to the previous page")
        back_action.triggered.connect(browser.backward)
        browser.backwardAvailable.connect(back_action.setEnabled)
        back_action.setEnabled(False)

        fwd_action = toolbar.addAction("Forward  \u25b6")
        fwd_action.setToolTip("Go to the next page")
        fwd_action.triggered.connect(browser.forward)
        browser.forwardAvailable.connect(fwd_action.setEnabled)
        fwd_action.setEnabled(False)

        toolbar.addSeparator()

        home_action = toolbar.addAction("\u2302  Home")
        home_action.setToolTip("Return to the documentation index")
        home_action.triggered.connect(browser.go_home)

        toolbar.addSeparator()

        self._html_title_label = QtWidgets.QLabel()
        toolbar.addWidget(self._html_title_label)
        browser.sourceChanged.connect(
            lambda url: self._html_title_label.setText(browser.documentTitle() or url.fileName())
        )

        self.setCentralWidget(browser)
        # Load home page after the window is assembled
        browser.go_home()

    def _build_no_docs_ui(self) -> None:
        """Show instructions when no documentation artefacts are found (tier 3)."""
        message = QtWidgets.QLabel(
            "<h3>Offline documentation not available</h3>"
            "<p>Neither compiled Qt Help files (<code>synaptipy.qhc</code>) nor"
            " pre-built HTML documentation were found.</p>"
            "<p>To build both and make them available for future runs:</p>"
            "<pre>  python scripts/build_offline_help.py</pre>"
            "<p>For development, building only the HTML is sufficient:</p>"
            "<pre>  cd docs &amp;&amp; make html</pre>"
            "<p>Online documentation is always available at "
            "<a href='https://synaptipy.readthedocs.io'>"
            "synaptipy.readthedocs.io</a>.</p>"
        )
        message.setOpenExternalLinks(True)
        message.setWordWrap(True)
        message.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
        message.setContentsMargins(24, 24, 24, 24)
        self.setCentralWidget(message)

    # ------------------------------------------------------------------
    # Navigation helpers (tier 1 only)
    # ------------------------------------------------------------------

    def _open_home_page(self) -> None:
        """Navigate to the documentation start page (QHelpEngine tier)."""
        for name in ("index.html", "user_guide.html"):
            url = QtCore.QUrl(f"qthelp://org.synaptipy.docs/doc/{name}")
            if self._engine.fileData(url):
                self._browser.setSource(url)
                return
        log.debug("HelpWindow: could not locate a home page in the Qt Help archive.")

    def _on_index_activated(self, url: QtCore.QUrl, keyword: str) -> None:  # noqa: ARG002
        """Navigate to *url* when a keyword index entry is activated."""
        self._browser.setSource(url)


# ---------------------------------------------------------------------------
# Convenience: re-use a single instance per session
# ---------------------------------------------------------------------------

_instance: Optional[HelpWindow] = None


def show_help_window(parent: Optional[QtWidgets.QWidget] = None) -> HelpWindow:
    """Return (and show/raise) the singleton :class:`HelpWindow`.

    The window is created lazily on first call.  Subsequent calls bring the
    existing window to the front without constructing a new one.

    Args:
        parent: Widget to use as parent on first creation only.

    Returns:
        The :class:`HelpWindow` instance.
    """
    global _instance
    if _instance is None or not _instance.isVisible():
        _instance = HelpWindow(parent)
    _instance.show()
    _instance.raise_()
    _instance.activateWindow()
    return _instance
