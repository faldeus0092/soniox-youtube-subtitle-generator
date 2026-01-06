def get_segment_info(segment):
    # 枕浮く。 え、聞いたことないよ。 嘘。 古文かな。 枕浮く。
    start = segment[0]["start_ms"]
    end = segment[-1]["end_ms"]
    text = "".join(seg["text"] for seg in segment)
    return start, end, text

def to_timestamp(ms):
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def soniox_to_srt(tokens: list[dict], min_duration: int, max_duration: int, max_chars_per_line:int):
    punctuation_segment = []
    cur = []
    # split at punctuation 、！　。
    # [['枕', '浮', 'く', '。'], [' ', 'え', '、', '聞', 'いた', 'こと', 'ない', 'よ', '。'], [' ', '嘘', '。'], [' ', '古', '文', 'か', 'な', '。'], [' ', '枕', '浮', 'く', '。'],
    for token in tokens:
        cur.append(token)
        if token["text"] in ["。","！","？","!","?"]:
            punctuation_segment.append(cur)
            cur = []
    if cur:
        punctuation_segment.append
        
    # merge the segmented subtitles as long as the duration doesn't exceed X seconds
    merged = []
    buf = None
    index = 1
    for segment in punctuation_segment:
        # segment ['枕', '浮', 'く', '。'],
        start, end, text = get_segment_info(segment)
        segment_duration = end-start
        if buf is None:
            buf = segment
            continue
        buf_start, buf_end, buf_text = get_segment_info(buf)
        combined_duration = end - buf_start
        combined_text_count = len(buf_text) + len(text)
        
        # only merge if not exceed the max duration or buffer is too short
        if (combined_duration <= max_duration or buf[-1]["end_ms"] - buf[0]["start_ms"] < min_duration) and combined_text_count <= max_chars_per_line:
            buf = buf + segment
        else:
            merged.append({
                "index": index,
                "start": buf_start,
                "end": buf_end,
                "text": buf_text
            })
            index += 1
            buf = segment
    if buf:
        buf_start, buf_end, buf_text = get_segment_info(buf)
        merged.append({
            "index": index,
            "start": buf_start,
            "end": buf_end,
            "text": buf_text
        })
    
    try:
        # with open(output_file_path, 'w') as f:
            section = []
            for lines in merged:
                section.append(str(lines["index"]))
                section.append(f"{to_timestamp(lines["start"])} --> {to_timestamp(lines["end"])}")
                section.append(lines["text"])
                section.append("")
            return "\n".join(section)
            # f.write("\n".join(section))
            # print(f"Successfully generated srt file {output_file_path}")
    except Exception as e:
            print(f"Failed to generate srt: {e}")
    return merged
