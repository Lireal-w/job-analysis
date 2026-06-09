"""重构验证脚本 - 检查关键修改点"""

import ast
import sys
from pathlib import Path

def check_xiaoyuan_spider():
    """检查xiaoyuan.py的关键修改"""
    file_path = Path("get_job/spiders/xiaoyuan.py")
    
    if not file_path.exists():
        print(f"ERROR: {file_path} not found")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = []
    
    # Check 1: No XiaoyuanJobItem instantiation in job parsing methods
    if "XiaoyuanJobItem()" in content:
        # Should only appear in imports, not in job parsing
        lines_with_item = [i+1 for i, line in enumerate(content.split('\n')) 
                          if 'XiaoyuanJobItem()' in line and 'import' not in line]
        if lines_with_item:
            print(f"WARNING: Found XiaoyuanJobItem() at lines: {lines_with_item}")
            checks.append(False)
        else:
            checks.append(True)
    else:
        checks.append(True)
    
    # Check 2: _platform field present in dict construction
    if "'_platform': 'xiaoyuan'" in content or '"_platform": "xiaoyuan"' in content:
        checks.append(True)
        print("OK: Found '_platform' field in dict")
    else:
        checks.append(False)
        print("ERROR: Missing '_platform' field")
    
    # Check 3: _raw_data field present
    if "'_raw_data':" in content or '"_raw_data":' in content:
        checks.append(True)
        print("OK: Found '_raw_data' field in dict")
    else:
        checks.append(False)
        print("ERROR: Missing '_raw_data' field")
    
    # Check 4: parse_job_detail handles dict
    if "isinstance(item, dict)" in content:
        checks.append(True)
        print("OK: parse_job_detail checks for dict type")
    else:
        checks.append(False)
        print("WARNING: parse_job_detail may not handle dict properly")
    
    return all(checks)


def check_pipelines():
    """检查pipelines.py的新增类"""
    file_path = Path("get_job/pipelines/pipelines.py")
    
    if not file_path.exists():
        print(f"ERROR: {file_path} not found")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = []
    
    # Check 1: RawDataPipeline class exists
    if "class RawDataPipeline:" in content:
        checks.append(True)
        print("OK: RawDataPipeline class found")
    else:
        checks.append(False)
        print("ERROR: RawDataPipeline class missing")
    
    # Check 2: UnifiedTransformPipeline class exists
    if "class UnifiedTransformPipeline:" in content:
        checks.append(True)
        print("OK: UnifiedTransformPipeline class found")
    else:
        checks.append(False)
        print("ERROR: UnifiedTransformPipeline class missing")
    
    # Check 3: _transform_xiaoyuan method exists
    if "_transform_xiaoyuan" in content:
        checks.append(True)
        print("OK: _transform_xiaoyuan method found")
    else:
        checks.append(False)
        print("ERROR: _transform_xiaoyuan method missing")
    
    return all(checks)


def check_settings():
    """检查settings.py的配置"""
    file_path = Path("get_job/settings.py")
    
    if not file_path.exists():
        print(f"ERROR: {file_path} not found")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = []
    
    # Check 1: RawDataPipeline in ITEM_PIPELINES
    if '"get_job.pipelines.RawDataPipeline": 50' in content:
        checks.append(True)
        print("OK: RawDataPipeline in ITEM_PIPELINES with priority 50")
    else:
        checks.append(False)
        print("ERROR: RawDataPipeline not in ITEM_PIPELINES")
    
    # Check 2: UnifiedTransformPipeline in ITEM_PIPELINES
    if '"get_job.pipelines.UnifiedTransformPipeline": 75' in content:
        checks.append(True)
        print("OK: UnifiedTransformPipeline in ITEM_PIPELINES with priority 75")
    else:
        checks.append(False)
        print("ERROR: UnifiedTransformPipeline not in ITEM_PIPELINES")
    
    # Check 3: RAW_DATA_ENABLED config
    if "RAW_DATA_ENABLED" in content:
        checks.append(True)
        print("OK: RAW_DATA_ENABLED config found")
    else:
        checks.append(False)
        print("ERROR: RAW_DATA_ENABLED config missing")
    
    # Check 4: RAW_DATA_COLLECTION config
    if "RAW_DATA_COLLECTION" in content:
        checks.append(True)
        print("OK: RAW_DATA_COLLECTION config found")
    else:
        checks.append(False)
        print("ERROR: RAW_DATA_COLLECTION config missing")
    
    return all(checks)


if __name__ == "__main__":
    print("=" * 60)
    print("智联校园招聘爬虫重构验证")
    print("=" * 60)
    
    print("\n[1/3] 检查 xiaoyuan.py...")
    spider_ok = check_xiaoyuan_spider()
    
    print("\n[2/3] 检查 pipelines.py...")
    pipelines_ok = check_pipelines()
    
    print("\n[3/3] 检查 settings.py...")
    settings_ok = check_settings()
    
    print("\n" + "=" * 60)
    if spider_ok and pipelines_ok and settings_ok:
        print("SUCCESS: 所有检查通过！")
        sys.exit(0)
    else:
        print("FAILED: 存在错误或警告，请检查上述输出")
        sys.exit(1)
