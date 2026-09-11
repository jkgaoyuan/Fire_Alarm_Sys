import subprocess
import os

drill_files = [
    "backend/app/models/drill.py",
    "backend/app/schemas/drill.py",
    "backend/app/crud/drill_crud.py",
    "backend/app/services/drill_service.py",
    "backend/app/api/v1/drills.py",
    "backend/alembic/versions/2026_09_11_0000-create_drill_tables.py",
    "backend/tests/test_drill_crud.py",
    "backend/scripts/init_data.py",
    "backend/app/api/v1/__init__.py",
    "backend/app/models/__init__.py",
    "frontend/src/api/drill.js",
    "frontend/src/api/__tests__/drill.spec.js",
    "frontend/src/views/drill/Event.vue",
    "frontend/src/views/drill/PlanFormDialog.vue",
    "frontend/src/views/drill/DetailDialog.vue",
    "frontend/src/views/drill/EvaluationDialog.vue",
    "frontend/src/views/drill/__tests__/EvaluationDialog.spec.js",
    "frontend/src/views/drill/__tests__/PlanFormDialog.spec.js",
    "frontend/src/utils/menu.js",
]

print("正在添加 Git 暂存区...")
added_count = 0
for f in drill_files:
    if os.path.exists(f):
        result = subprocess.run(['git', 'add', f], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"OK: {f}")
            added_count += 1
        else:
            print(f"FAIL: {f} - {result.stderr.strip()}")
    
print(f"\n成功添加了 {added_count}/{len(drill_files)} 个文件")
print("\n现在执行 commit...")

commit_result = subprocess.run(
    ['git', 'commit', '-m', 'feat: Complete 3.8 Fire Drill Module Development'],
    capture_output=True, 
    text=True
)
print(commit_result.stdout)
if commit_result.stderr:
    print("Stderr:", commit_result.stderr)
print("Commit completed!")
