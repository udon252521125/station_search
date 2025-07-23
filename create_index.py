#!/usr/bin/env python3
"""
駅データのインデックス作成スクリプト
「位置×文字→駅IDリスト」の辞書を事前計算してJSONファイルに保存
"""

import pandas as pd
import json
import jaconv
from collections import defaultdict
import time

def create_station_index(csv_file="station20250604free.csv"):
    """
    駅データから位置×文字のインデックスを作成
    
    Args:
        csv_file: 駅データのCSVファイル
        
    Returns:
        tuple: (hiragana_index, katakana_index, station_data)
    """
    print(f"駅データを読み込み中: {csv_file}")
    df = pd.read_csv(csv_file)
    print(f"データ件数: {len(df):,} 件")
    
    # 路線・事業者情報を読み込み
    try:
        print("路線・事業者データを読み込み中: eki.csv")
        route_df = pd.read_csv("eki.csv")
        route_mapping = dict(zip(route_df['路線コード'], route_df['路線名']))
        operator_mapping = dict(zip(route_df['路線コード'], route_df['事業者']))
        
        # 路線名と事業者名をマッピング
        df['route_name'] = df['line_cd'].map(route_mapping).fillna("不明")
        df['operator_name'] = df['line_cd'].map(operator_mapping).fillna("不明")
        print(f"路線データマッピング完了: {len(route_mapping)} 路線")
    except Exception as e:
        print(f"⚠️ 路線データ(eki.csv)の読み込みに失敗: {e}")
        df['route_name'] = "不明"
        df['operator_name'] = "不明"
    
    # 都道府県名を追加（master_dataがある場合）
    try:
        from master_data import PREFECTURE_CODE_TO_NAME
        df['prefecture'] = df['pref_cd'].map(PREFECTURE_CODE_TO_NAME)
        print("都道府県名マッピング完了")
    except Exception as e:
        print(f"⚠️ 都道府県データの読み込みに失敗: {e}")
        # 都道府県コードをそのまま使用
        df['prefecture'] = df['pref_cd'].astype(str) + "番"
    
    # インデックス初期化
    hiragana_index = defaultdict(lambda: defaultdict(list))
    katakana_index = defaultdict(lambda: defaultdict(list))
    
    print("インデックス作成中...")
    start_time = time.time()
    
    for idx, row in df.iterrows():
        if idx % 1000 == 0:
            print(f"処理中: {idx:,} / {len(df):,} ({idx/len(df)*100:.1f}%)")
        
        station_name = row['station_name']
        
        # ひらがな/漢字用インデックス（カタカナをひらがなに変換）
        # 駅名全体をひらがなに変換してから、各文字位置でインデックス作成
        hiragana_name = jaconv.kata2hira(station_name)
        for pos, char in enumerate(hiragana_name):
            hiragana_index[pos][char].append(idx)
        
        # カタカナ保持用インデックス（変換なし）
        # 駅名をそのまま使用して、各文字位置でインデックス作成
        for pos, char in enumerate(station_name):
            katakana_index[pos][char].append(idx)
    
    # defaultdictを通常の辞書に変換
    hiragana_dict = {pos: dict(chars) for pos, chars in hiragana_index.items()}
    katakana_dict = {pos: dict(chars) for pos, chars in katakana_index.items()}
    
    elapsed_time = time.time() - start_time
    print(f"インデックス作成完了: {elapsed_time:.2f}秒")
    
    # 統計情報
    total_hiragana_entries = sum(len(chars) for chars in hiragana_dict.values())
    total_katakana_entries = sum(len(chars) for chars in katakana_dict.values())
    print(f"ひらがなインデックス: {len(hiragana_dict)} 位置, {total_hiragana_entries} エントリ")
    print(f"カタカナインデックス: {len(katakana_dict)} 位置, {total_katakana_entries} エントリ")
    
    return hiragana_dict, katakana_dict, df

def save_index_to_files(hiragana_index, katakana_index, df):
    """
    インデックスと駅データをファイルに保存
    """
    print("ファイル保存中...")
    
    # インデックスをJSONで保存
    with open('station_hiragana_index.json', 'w', encoding='utf-8') as f:
        json.dump(hiragana_index, f, ensure_ascii=False, separators=(',', ':'))
    
    with open('station_katakana_index.json', 'w', encoding='utf-8') as f:
        json.dump(katakana_index, f, ensure_ascii=False, separators=(',', ':'))
    
    # 駅データをCSVで保存（全ての列を保持）
    df.to_csv('station_data_indexed.csv', index=False, encoding='utf-8')
    
    print("保存完了:")
    print("- station_hiragana_index.json")
    print("- station_katakana_index.json") 
    print("- station_data_indexed.csv")
    
    # 保存された列の確認
    print(f"保存された列: {list(df.columns)}")
    print(f"データ行数: {len(df):,}")
    
    # 路線・事業者情報の統計
    unique_routes = df['route_name'].nunique()
    unique_operators = df['operator_name'].nunique()
    unknown_routes = (df['route_name'] == '不明').sum()
    unknown_operators = (df['operator_name'] == '不明').sum()
    
    print(f"路線数: {unique_routes} (不明: {unknown_routes}件)")
    print(f"事業者数: {unique_operators} (不明: {unknown_operators}件)")

def test_index_performance(hiragana_index, katakana_index, df):
    """
    インデックスの検索性能をテスト
    """
    print("\n=== 性能テスト ===")
    
    test_queries = [
        ("し", 1),   # 2文字目に「し」
        ("の", 2),   # 3文字目に「の」
        ("大", 0),   # 1文字目に「大」
        ("駅", 1),   # 2文字目に「駅」
    ]
    
    for char, pos in test_queries:
        start_time = time.time()
        
        # インデックス検索
        if pos in hiragana_index and char in hiragana_index[pos]:
            result_count = len(hiragana_index[pos][char])
        else:
            result_count = 0
        
        elapsed_time = time.time() - start_time
        print(f"位置{pos}文字目「{char}」: {result_count}件 ({elapsed_time*1000:.3f}ms)")

def main():
    """
    メイン処理
    """
    print("=== 駅データインデックス作成ツール ===")
    
    try:
        # インデックス作成
        hiragana_index, katakana_index, df = create_station_index()
        
        # ファイル保存
        save_index_to_files(hiragana_index, katakana_index, df)
        
        # 性能テスト
        test_index_performance(hiragana_index, katakana_index, df)
        
        print("\n✅ インデックス作成が完了しました！")
        print("station_search_gui.py でこれらのファイルを使用して高速検索が可能になります。")
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
