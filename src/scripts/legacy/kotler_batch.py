#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理科特勒营销管理 81 集
使用 B 站 API + Whisper 转录
"""

import json
import subprocess
import os
import re
from pathlib import Path
from datetime import datetime
import time

# 配置
VAULT_ROOT = Path.home() / "obsidian" / "all about xia"
OUTPUT_DIR = Path("/tmp/kotler_batch")
VAULT_TARGET = "03-方法学与工具"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 商汤 API 配置
SENSENOVA_API_KEY = "sk-jCFNAPgMp1TCRCTkJ1PDfuqtgxxOJKR7"  # 已验证有效的API Key
SENSENOVA_API_BASE = "https://token.sensenova.cn/v1"
SENSENOVA_MODEL = "deepseek-v4-flash"

if not SENSENOVA_API_KEY:
    print("❌ 错误: SENSENOVA_API_KEY 未设置")
    exit(1)


def get_video_url(bvid, cid):
    """通过 B 站 API 获取视频 URL"""
    api_url = f"https://api.bilibili.com/x/player/playurl?cid={cid}&bvid={bvid}&qn=16&type=&otype=json&platform=html5"
    result = subprocess.run(
        ["curl", "-s", "--compressed",
         "-H", "User-Agent: Mozilla/5.0",
         "-H", f"Referer: https://www.bilibili.com/video/{bvid}/",
         api_url],
        shell=False, capture_output=True, text=True, timeout=300
    )
    
    try:
        data = json.loads(result.stdout)
        if data.get('data') and data['data'].get('durl'):
            return data['data']['durl'][0]['url']
    except Exception:
        pass
    return None


def download_video(video_url, output_path):
    """下载视频"""
    if not video_url:
        return False
    result = subprocess.run(
        ["curl", "-sL", "--compressed",
         "-H", "User-Agent: Mozilla/5.0",
         "-H", "Referer: https://www.bilibili.com/",
         "-o", output_path, video_url],
        shell=False, capture_output=True, text=True, timeout=600
    )
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"   下载大小: {size} bytes")
        return size > 100000  # 至少 100KB
    return False


def transcribe_audio(video_path, output_path):
    """使用 Whisper 转录"""
    try:
        import whisper
        model = whisper.load_model("base")
        # 转换为字符串路径
        video_path_str = str(video_path)
        result = model.transcribe(video_path_str, language="zh")
        
        def format_timestamp(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        
        srt_lines = []
        for i, seg in enumerate(result['segments'], 1):
            srt_lines.append(f"{i}\n{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n{seg['text'].strip()}\n")
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(srt_lines))
        return True
    except Exception as e:
        print(f"   Whisper 转录失败: {e}")
        return False


def summarize_with_ai(subtitle_path, episode_num, title):
    """使用商汤 AI 总结"""
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=SENSENOVA_API_KEY,
            base_url=SENSENOVA_API_BASE,
        )
        
        with open(subtitle_path, 'r') as f:
            content = f.read()
        
        text_only = re.sub(r'\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n', '', content)
        text_only = text_only.strip()
        
        prompt = f"""你是一位知识整理专家。请对以下视频字幕进行结构化总结：

视频：《科特勒营销管理》第 {episode_num} 集 - {title}

字幕内容：
{text_only[:15000]}

要求：
1. 提取核心知识点，按逻辑分组
2. 保留关键定义和框架
3. 标注时间戳
4. 输出 Markdown 格式

输出格式：
## 核心主题
[主题描述]

## 知识点
### [知识点 1]
- 内容...
- 时间戳：[XX:XX]

## 关键定义
- [定义 1] — [时间戳]

## 行动项/思考
- [思考 1]
"""
        
        response = client.chat.completions.create(
            model=SENSENOVA_MODEL,
            messages=[
                {"role": "system", "content": "你是一位知识整理专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=4000,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"   AI 总结失败: {e}")
        return None


def ingest_note(note_content, title, episode_num):
    """入库笔记"""
    target_dir = VAULT_ROOT / VAULT_TARGET
    target_dir.mkdir(parents=True, exist_ok=True)
    
    clean_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:40]
    filename = f"{episode_num:02d}-{clean_title}.md"
    filepath = target_dir / filename
    
    counter = 1
    while filepath.exists():
        filename = f"{episode_num:02d}-{clean_title}_{counter}.md"
        filepath = target_dir / filename
        counter += 1
    
    with open(filepath, 'w') as f:
        f.write(note_content)
    
    return str(filepath)


def process_episode(bvid, cid, episode_num, title):
    """处理单集"""
    print(f"\n🎬 处理第 {episode_num} 集: {title[:50]}...")
    
    video_url = get_video_url(bvid, cid)
    if not video_url:
        print("   ❌ 无法获取视频 URL")
        return False, "无法获取视频 URL"
    
    video_path = OUTPUT_DIR / f"ep{episode_num}.mp4"
    if not download_video(video_url, video_path):
        print("   ❌ 视频下载失败")
        return False, "视频下载失败"
    
    size_mb = video_path.stat().st_size / 1024 / 1024
    print(f"   ✅ 视频已下载: {size_mb:.1f} MB")
    
    subtitle_path = OUTPUT_DIR / f"ep{episode_num}.srt"
    if not transcribe_audio(video_path, subtitle_path):
        print("   ❌ 转录失败")
        return False, "转录失败"
    
    with open(subtitle_path, 'r') as f:
        subtitle_content = f.read()
    text_only = re.sub(r'\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n', '', subtitle_content)
    char_count = len(text_only.strip())
    print(f"   ✅ 转录完成: {char_count} 字")
    
    print("   🧠 AI 总结中...")
    summary = summarize_with_ai(subtitle_path, episode_num, title)
    if not summary:
        print("   ❌ AI 总结失败")
        return False, "AI 总结失败"
    
    note_content = f"""---
title: 《科特勒营销管理》第 {episode_num} 集 - {title}
date: {datetime.now().strftime('%Y-%m-%d')}
type: education
source: https://b23.tv/FyVg8Da
status: draft
tags: [视频, 教育, 营销, 科特勒]
video_type: 教育
episode: {episode_num}
---

# 《科特勒营销管理》第 {episode_num} 集 - {title}

> 来源：[B 站](https://b23.tv/FyVg8Da)
> 入库日期：{datetime.now().strftime('%Y-%m-%d')}
> 字幕字数：{char_count} 字

---

## 📌 核心主题

{summary}

---

## 📎 原文字幕

> 完整字幕文件：`{subtitle_path}`
"""
    
    ingested_path = ingest_note(note_content, title, episode_num)
    print(f"   ✅ 已入库: {ingested_path}")
    
    video_path.unlink(missing_ok=True)
    
    return True, ingested_path


def main():
    """主程序"""
    print("="*60)
    print("📺 科特勒营销管理 批量处理")
    print("="*60)
    
    bvid = "BV1FtvCeTE6Q"
    
    with open("/tmp/kotler_cids.json", 'r') as f:
        cids_data = json.load(f)
    
    cids = cids_data['cids']
    
    success_count = 0
    fail_count = 0
    fail_reasons = {}
    
    # 处理第 2-79 集（索引 1-78）
    for idx in range(1, 79):
        episode_num = idx + 1
        cid = cids[idx]
        title = f"第 {episode_num} 节"
        
        success, result = process_episode(bvid, cid, episode_num, title)
        
        if success:
            success_count += 1
        else:
            fail_count += 1
            fail_reasons[episode_num] = result
        
        if idx < 78:
            print("   ⏳ 等待 5 秒...")
            time.sleep(5)
    
    print("\n" + "="*60)
    print("✅ 处理完成")
    print("="*60)
    print(f"   成功：{success_count} 集")
    print(f"   失败：{fail_count} 集")
    
    if fail_reasons:
        print("\n失败详情:")
        for ep_num, reason in fail_reasons.items():
            print(f"   第 {ep_num} 集: {reason}")


if __name__ == "__main__":
    main()
