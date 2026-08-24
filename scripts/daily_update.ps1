# 경쟁사 레이더 일일 자동 갱신 (로컬 실행)
# Windows 작업 스케줄러가 매일 09:00 KST에 이 스크립트를 실행한다.
# 클라우드 예약 작업은 뉴스 도메인 접근이 막혀 있어(EGRESS_BLOCKED) 로컬에서 실행한다.

$ProjectDir = "C:\Users\netcruz.N-344\Music\클로드작업폴더\5.경쟁사 분석용\99.결과물\경쟁사레이더"
$LogFile = Join-Path $ProjectDir "data\daily_update.log"

Set-Location $ProjectDir
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LogFile -Value "`n===== $timestamp 실행 시작 ====="

python scripts\collect.py *>> $LogFile
if ($LASTEXITCODE -ne 0) {
    Add-Content -Path $LogFile -Value "collect.py 실패 (exit $LASTEXITCODE) - 중단"
    exit 1
}

python scripts\render.py *>> $LogFile
if ($LASTEXITCODE -ne 0) {
    Add-Content -Path $LogFile -Value "render.py 실패 (exit $LASTEXITCODE) - 중단"
    exit 1
}

git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $today = Get-Date -Format "yyyy-MM-dd"
    git commit -m "일일 자동 갱신 $today" *>> $LogFile
    git push *>> $LogFile
    Add-Content -Path $LogFile -Value "변경 사항 커밋 및 푸시 완료"
} else {
    Add-Content -Path $LogFile -Value "변경 사항 없음, 커밋 생략"
}
Add-Content -Path $LogFile -Value "===== 실행 완료 ====="

