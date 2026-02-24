@ECHO OFF
REM Windows build script for Sphinx documentation.
REM Builds using the 'synaptipy' conda environment.

pushd %~dp0

set CONDA_ENV=synaptipy
set SPHINXBUILD=conda run -n %CONDA_ENV% sphinx-build
set SOURCEDIR=.
set BUILDDIR=_build

if "%1" == "" goto html
if "%1" == "clean" goto clean

%SPHINXBUILD% -b %1 %SOURCEDIR% %BUILDDIR%\%1 %SPHINXOPTS% %O%
goto end

:html
%SPHINXBUILD% -b html %SOURCEDIR% %BUILDDIR%\html %SPHINXOPTS% %O%
echo.
echo Build finished. HTML pages are in %BUILDDIR%\html.
goto end

:clean
rmdir /s /q %BUILDDIR% 2>NUL
echo Build directory cleaned.
goto end

:end
popd
