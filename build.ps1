
$package_name = "TextTranslator"

$version = Invoke-Expression ('.\venv\Scripts\python.exe -c "from main import __version__;print(__version__)"')

New-Item -ErrorAction Ignore -ItemType Directory -Path release
Set-Location .\release
Invoke-Expression ("..\venv\Scripts\pyinstaller.exe ..\main.spec -y")

Write-Output  "build version: $version"

# remove old package
if (Test-Path -Path $package_name) {
    Remove-Item -Recurse -Force $package_name
}


Move-Item -Force .\dist\$package_name .\

# copy font and config
Copy-Item -Force -Recurse ..\config  .\$package_name\
Copy-Item -Force -Recurse ..\font .\$package_name\
Copy-Item -Force ..\server-list.ini .\$package_name\

# create zip package
$zipname = $package_name + "_" + $version +"_windows.zip"
Compress-Archive -Force -Path $package_name -DestinationPath $zipname


Copy-Item -Force ..\config.ini .\$package_name\

Pause