#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""平台 check_genome_files.py 检查逻辑的**逐字存档副本**（仅用于本任务验收）。

来源：服务器 `/var/www/html/Script/check_genome_files.py`
（WORKFLOW_GAP.md §1 记录 md5 `d774445172714d0d6b9127d4a21cc2a0`；
本机副本 /tmp/wm_server/check_genome_files.py 在验收时已被清理，故逐字存档
`check_fasta_headers` / `check_gff3` / `check_fasta_ids` 三个函数，逻辑未改动）。

为什么单独存档：平台脚本 `main()` 需要 ${MYTAG}.fa/.gff3/.cds/.pep 四件套齐全才整跑，
本任务未下载 4×~4.7 GB 基因组 FASTA，因此只调用与产物直接相关的三个检查函数
（其中 `check_gff3` 即 G2 闸门对 `.gff3` 的硬性规则）。

用法：
    python3 platform_equiv_check.py FILE [FILE ...]
按扩展名分派：.gff3/.gff3.gz -> check_gff3；.fa/.fa.gz -> check_fasta_headers；
.cds/.pep(.gz) -> check_fasta_ids。退出码 0=全部通过，1=有错误。
（.gz 文件会先解压到临时文件再检查，因为平台原函数只接受普通文件路径。）
"""

import gzip
import os
import re
import sys
import tempfile


# ---------------------------------------------------------------------------
# 以下三个函数逐字复制自平台 check_genome_files.py（未改动逻辑）
# ---------------------------------------------------------------------------

def check_fasta_headers(filename):
    """
    检查 FASTA 文件（.fa）：
    - 序列头必须以 'Chr' 开头（忽略大小写时包含 contig 或 scaffold 的序列）
    """
    errors = []
    with open(filename, 'r') as f:
        for line in f:
            if line.startswith('>'):
                header = line[1:].strip()
                # 若包含 contig/scaffold 则跳过
                if 'contig' in header.lower() or 'scaffold' in header.lower():
                    continue
                if not header.startswith('Chr'):
                    errors.append("序列头 '%s' 不是以 'Chr' 开头" % header)
    return errors


def check_gff3(filename):
    """
    检查 GFF3 文件：
    - 第一列以 'Chr' 开头
    - mRNA 行的 ID= 属性以 .数字 结尾
    """
    errors = []
    with open(filename, 'r') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) < 9:
                continue
            seqid = parts[0]
            if not seqid.startswith('Chr'):
                errors.append("序列ID '%s' 不是以 'Chr' 开头" % seqid)
            # 仅检查 mRNA 行
            if parts[2] == 'mRNA':
                attrs = parts[8]
                id_match = re.search(r'ID=([^;]+)', attrs)
                if id_match:
                    id_val = id_match.group(1)
                    if not re.search(r'\.\d+$', id_val):
                        errors.append("mRNA ID '%s' 不是以 .数字 结尾" % id_val)
                else:
                    errors.append("mRNA 行缺少 ID 属性: %s" % line.strip())
    return errors


def check_fasta_ids(filename):
    """
    检查 CDS/PEP FASTA 文件：
    - 序列 ID（> 后第一个空格前的内容）以 .数字 结尾
    """
    errors = []
    with open(filename, 'r') as f:
        for line in f:
            if line.startswith('>'):
                header = line[1:].strip()
                id_part = header.split()[0]  # 取第一个空格前的部分
                if not re.search(r'\.\d+$', id_part):
                    errors.append("序列 ID '%s' 不是以 .数字 结尾" % id_part)
    return errors


# ---------------------------------------------------------------------------
# 驱动（本任务补充，非平台原件）
# ---------------------------------------------------------------------------

def _open_any(path):
    """返回 (临时文件路径, 是否需要删除)。平台函数只接受普通文件。"""
    name = path
    low = path.lower()
    if low.endswith('.gz'):
        fd, tmp = tempfile.mkstemp(suffix=os.path.basename(path)[:-3])
        with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as fi, \
                os.fdopen(fd, 'w', encoding='utf-8') as fo:
            fo.write(fi.read())
        return tmp, True
    return name, False


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    all_ok = True
    for path in argv[1:]:
        tmp, cleanup = _open_any(path)
        try:
            low = path.lower()
            if '.gff3' in low:
                func, label = check_gff3, 'check_gff3'
            elif low.endswith('.fa') or low.endswith('.fa.gz') or '.fna' in low:
                func, label = check_fasta_headers, 'check_fasta_headers'
            elif '.cds' in low or '.pep' in low:
                func, label = check_fasta_ids, 'check_fasta_ids'
            else:
                print('[SKIP] 未知扩展名: %s' % path)
                continue
            errors = func(tmp)
            if errors:
                all_ok = False
                print('[FAIL] %s (%s): %d errors' % (path, label, len(errors)))
                for err in errors[:10]:
                    print('        %s' % err)
            else:
                print('[PASS] %s (%s)' % (path, label))
        finally:
            if cleanup and os.path.exists(tmp):
                os.remove(tmp)
    print('PLATFORM_EQUIV_RESULT: %s' % ('PASS' if all_ok else 'FAIL'))
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
