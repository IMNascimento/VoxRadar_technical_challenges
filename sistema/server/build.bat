@echo off
rem Recompila KwaiSign.java (so precisa rodar se voce editar src\com\kwai\sig3\KwaiSign.java).
cd /d %~dp0
set "JAVA_HOME=%~dp0jdk8"
set "PATH=%JAVA_HOME%\bin;%PATH%"
javac -cp "classes;lib\*" -d classes src\com\kwai\sig3\KwaiSign.java
echo EXITCODE=%ERRORLEVEL%
