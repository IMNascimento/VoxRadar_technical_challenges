@echo off
rem Sobe o servico local de assinatura __NS_sig3 (ver ..\PESQUISA.md).
rem Uso:  run.bat --serve 8765
cd /d %~dp0
set "JAVA_HOME=%~dp0jdk8"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "CLASSPATH=classes;lib\*"
java com.kwai.sig3.KwaiSign %*
echo EXITCODE=%ERRORLEVEL%
