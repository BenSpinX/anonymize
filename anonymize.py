import os
import argparse
import hashlib
import csv
from pathlib import Path
from pydicom import dcmread
from pydicom.uid import generate_uid
from pydicom.errors import InvalidDicomError

# 常见需要清除或替换的 DICOM 标签名（标签存在则处理）
# "SeriesDescription" 已从清除列表中移除，以保留该信息
FIELDS_TO_CLEAR = [
    "PatientName", "PatientID", "PatientBirthDate", "PatientSex",
    "PatientAddress", "OtherPatientIDs", "OtherPatientNames",
    "EthnicGroup", "PatientTelephoneNumbers", "AccessionNumber",
    "InstitutionName", "InstitutionAddress", "ReferringPhysicianName",
    "StudyID", "StudyDescription", "PerformingPhysicianName",
    "OperatorsName", "RequestingPhysician", "StudyComments",
]

UID_FIELDS = [
    "StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID",
    "MediaStorageSOPInstanceUID"
]

def make_pseudonym(source, salt="anon"):
    """从字符串生成可重复的伪名（字母数字下划线）"""
    if source is None:
        source = ""
    h = hashlib.sha256((str(source) + salt).encode("utf-8")).hexdigest()
    # 取前12位作为简短伪名
    return "anon_" + h[:12]

def anonymize_dataset(ds, pseudomap=None, uid_map=None, salt="anon"):
    """对单个 pydicom Dataset 做匿名化，返回用于映射的 key(原始ID或Name) 和 新的 subject name"""
    if uid_map is None:
        uid_map = {}    
    # 先移除私有标签。移除私有标签有可能会导致一个序列转nii时被分成两个，
    # 因此这里注释掉，保留私有标签
    # try:
    #     ds.remove_private_tags()
    # except Exception:
    #     pass

    # 尝试找到合适的原始标识符（优先 PatientID, 否则 PatientName）
    orig_id = None
    try:
        if getattr(ds, "PatientID", None):
            orig_id = str(ds.PatientID)
        elif getattr(ds, "PatientName", None):
            orig_id = str(ds.PatientName)
    except Exception:
        orig_id = None

    pseud = make_pseudonym(orig_id or "unknown", salt=salt)

    # 清空或替换常规字段
    for name in FIELDS_TO_CLEAR:
        if hasattr(ds, name):
            # 对 PatientName、PatientID 等使用 pseud，其他字段清空
            if name in ("PatientName", "PatientID"):
                try:
                    setattr(ds, name, pseud)
                except Exception:
                    ds.data_element(name).value = pseud
            else:
                try:
                    setattr(ds, name, "")
                except Exception:
                    try:
                        ds.data_element(name).value = ""
                    except Exception:
                        pass

    # 保证 StudyInstanceUID / SeriesInstanceUID 在同一 series/study 中一致
    try:
        orig_study_uid = getattr(ds, "StudyInstanceUID", None)
        if orig_study_uid:
            key = ("study", str(orig_study_uid))
            new = uid_map.get(key)
            if new is None:
                new = generate_uid()
                uid_map[key] = new
            ds.StudyInstanceUID = new
    except Exception:
        pass

    try:
        orig_series_uid = getattr(ds, "SeriesInstanceUID", None)
        if orig_series_uid:
            key = ("series", str(orig_series_uid))
            new = uid_map.get(key)
            if new is None:
                new = generate_uid()
                uid_map[key] = new
            ds.SeriesInstanceUID = new
    except Exception:
        pass

    # 为每个实例生成唯一 SOPInstanceUID
    try:
        ds.SOPInstanceUID = generate_uid()
    except Exception:
        try:
            ds.data_element("SOPInstanceUID").value = generate_uid()
        except Exception:
            pass

    # 更新 file_meta 中的 MediaStorageSOPInstanceUID（与 SOPInstanceUID 对应）
    try:
        if not ds.file_meta:
            ds.file_meta = ds.file_meta  # noop 保持兼容
        if getattr(ds, "SOPInstanceUID", None):
            if ds.file_meta is not None:
                ds.file_meta.MediaStorageSOPInstanceUID = str(ds.SOPInstanceUID)
    except Exception:
        pass

    # 返回原始 id/name（可为 None）和伪名，uid_map 由调用者持有以保证一致性
    if pseudomap is not None:
        pseudomap[orig_id] = pseud
    return orig_id, pseud

def is_dicom_file(path):
    try:
        with open(path, "rb") as f:
            pre = f.read(132)
            return pre[128:132] == b"DICM"
    except Exception:
        return False

def process_folder(in_dir, out_dir, recursive=True, map_file=None, uid_map=None, salt="anon"):
    out_directory = out_dir
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)
    mapping = {}  # 原始 -> pseud
    errors = []   # 记录错误的文件路径

    # uid_map 用于在同一运行中保持 Study/Series UID 映射一致（避免每个文件生成不同 SeriesInstanceUID）
    uid_map = {}    

    # 先收集待处理文件列表（支持 recursive 开关）
    file_list = []
    for root, dirs, files in os.walk(in_dir):
        for fname in files:
            file_list.append(Path(root) / fname)
        if not recursive:
            break

    total = len(file_list)
    if total == 0:
        print("Process: 100%")
        return mapping

    processed = 0
    for src_path in file_list:
        rel = src_path.parent.relative_to(in_dir)
        target_root = out_dir.joinpath(rel)
        # print("Message: src_path:", src_path)
        target_root.mkdir(parents=True, exist_ok=True)
        dst_path = target_root / src_path.name
        # print("Message: dst_path:", dst_path)

        base = Path("/spinx/v0/input")
        try:
            # 非 DICOM 文件 -> 视为错误（不复制、不处理）
            if not is_dicom_file(src_path):
                print("non-DICOM file encountered:", src_path.relative_to(base))
                errors.append(src_path.relative_to(base))
                processed += 1
                percent = int(processed * 100 / total)
                print(f"Process: {percent}%")
                continue

            ds = dcmread(src_path, force=True)
            orig, pseud = anonymize_dataset(ds, pseudomap=mapping, uid_map=uid_map, salt=salt)
            ds.save_as(str(dst_path))
        except InvalidDicomError:
            print("Error: Invalid DICOM file:", src_path.relative_to(base))
            errors.append(src_path.relative_to(base))
        except Exception as e:
            print("Warning: failed to process", src_path.relative_to(base), ":", e)
            errors.append(src_path.relative_to(base))

        processed += 1
        percent = int(processed * 100 / total)
        print(f"Process: {percent}%")

    # 写 mapping csv（如果需要）
    if map_file:
        try:
            output_map_file = os.path.join(out_directory, "mapping.csv")
            with open(output_map_file, "w", newline="", encoding="utf-8") as csvf:
                writer = csv.writer(csvf)
                writer.writerow(["original_id_or_name", "pseudonym"])
                for orig, pseud in mapping.items():
                    writer.writerow([orig if orig is not None else "", pseud])
        except Exception as e:
            print("Error: failed to write mapping file:", e)
            errors.append(f"mapfile:{e}")

    # 若存在任何错误，则视为处理失败并抛出异常（使进程返回非0）
    if errors:
        print(f"Message: {len(errors)} files failed during processing, see output/errors.csv for details.")
        output_error_file = os.path.join(out_directory, "errors.csv")
        with open(output_error_file, "w", newline="", encoding="utf-8") as csvf:
            writer = csv.writer(csvf)
            writer.writerow(["error file paths"])
            for orig in errors:
                writer.writerow([orig])

    return mapping

def parse_args():
    p = argparse.ArgumentParser(description="Batch anonymize DICOM files (writes to output dir).")
    p.add_argument("--input", "-i", required=True, help="Input folder (containing DICOM files).")
    p.add_argument("--output", "-o", required=True, help="Output folder to write anonymized files.")
    p.add_argument("--map-file", "-m", help="Optional CSV map file to save original -> pseudonym mapping.")
    p.add_argument("--recursive", "-r", action="store_true", help="Recursively process subfolders.")
    p.add_argument("--salt", default="anon", help="Salt used for pseudonym generation (default 'anon').")
    return p.parse_args()

def main():
    args = parse_args()
    out = args.output
    os.makedirs(out, exist_ok=True)
    print("Message: Starting anonymization process...")
    mapping = process_folder(args.input, out, recursive=args.recursive, map_file=args.map_file,
                            salt=args.salt)
    print("Message: Done. Anonymized files written to Output folder.")
    if args.map_file:
        print("Message: Mapping written to Output folder")

if __name__ == "__main__":
    main()