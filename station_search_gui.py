import streamlit as st
import pandas as pd
import json
import re
import jaconv
from typing import List, Dict, Tuple, Optional
import io
import os
from master_data import LINE_MAPPING, OPERATOR_MAPPING, REGION_MAPPING, PREFECTURE_CODE_TO_NAME


@st.cache_data
def load_precomputed_index():
    """
    事前計算されたインデックスファイルを読み込み
    
    Returns:
        tuple: (hiragana_index, katakana_i                    # 検索範囲を決定
                    station_pref_cd = station_data.get('pref_cd', 0)
                    if selected_prefecture_codes and station_pref_cd in selected_prefecture_codes:
                        search_scope = '🔵 選択地域内'
                    else:
                        search_scope = '🔴 全国'df) or (None, None, None)
    """
    try:
        # インデックスファイルの存在確認
        hiragana_file = 'station_hiragana_index.json'
        katakana_file = 'station_katakana_index.json'
        data_file = 'station_data_indexed.csv'
        
        if not all(os.path.exists(f) for f in [hiragana_file, katakana_file, data_file]):
            return None, None, None
        
        # インデックス読み込み
        with open(hiragana_file, 'r', encoding='utf-8') as f:
            hiragana_index = json.load(f)
        
        with open(katakana_file, 'r', encoding='utf-8') as f:
            katakana_index = json.load(f)
        
        # 駅データ読み込み
        df = pd.read_csv(data_file)
        
        # キーを整数に変換（JSONは文字列キーになるため）
        hiragana_index = {int(k): v for k, v in hiragana_index.items()}
        katakana_index = {int(k): v for k, v in katakana_index.items()}
        
        return hiragana_index, katakana_index, df
        
    except Exception as e:
        st.warning(f"インデックスファイルの読み込みに失敗: {e}")
        return None, None, None


def find_stations_by_index(station_index: Dict, char: str, position: int, df: pd.DataFrame) -> List[Dict]:
    """
    インデックスを使用した高速駅検索
    
    Args:
        station_index: 事前作成されたインデックス
        char: 検索文字
        position: 位置
        df: 駅データ
    
    Returns:
        該当する駅の辞書リスト
    """
    if position not in station_index or char not in station_index[position]:
        return []
    
    # インデックスから駅IDを取得し、対応する駅データを返す
    station_indices = station_index[position][char]
    matching_stations = []
    
    for idx in station_indices:
        if idx < len(df):
            station_data = df.iloc[idx].to_dict()
            
            # 実際の駅名から該当位置の文字を取得して検証
            station_name = station_data.get('station_name', '')
            if position < len(station_name):
                # 実際の駅名の指定位置の文字を取得
                actual_char_at_position = station_name[position]
                
                # インデックスが正しく動作しているか確認（デバッグ用）
                # この文字が検索文字と一致するかチェック
                normalized_actual = jaconv.kata2hira(actual_char_at_position)
                normalized_search = jaconv.kata2hira(char)
                
                if normalized_actual == normalized_search:
                    station_data['actual_char'] = actual_char_at_position
                    matching_stations.append(station_data)
            # position >= len(station_name)の場合はスキップ（インデックスエラーの可能性）
    
    return matching_stations



def get_prefecture_options():
    """都道府県とその地方区分のオプションを取得（都道府県コード順）"""
    options = []
    
    # 地方区分をオプションに追加
    for region_name in REGION_MAPPING.keys():
        options.append(f"【{region_name}】")
    
    # 都道府県を都道府県コード順で追加
    for code in sorted(PREFECTURE_CODE_TO_NAME.keys()):
        options.append(PREFECTURE_CODE_TO_NAME[code])
    
    return options

def get_selected_prefecture_codes(selected_options):
    """選択されたオプションから都道府県コードのリストを取得"""
    pref_codes = []
    
    for option in selected_options:
        if option.startswith("【") and option.endswith("】"):
            # 地方区分の場合
            region_name = option[1:-1]  # 【】を除去
            if region_name in REGION_MAPPING:
                pref_codes.extend(REGION_MAPPING[region_name])
        else:
            # 個別都道府県の場合
            for code, name in PREFECTURE_CODE_TO_NAME.items():
                if name == option:
                    pref_codes.append(code)
                    break
    
    return list(set(pref_codes))  # 重複排除


def load_station_data(csv_file=None) -> pd.DataFrame:
    """
    駅データを読み込み、必要な列の存在確認とデータ整形を行う
    """
    try:
        if csv_file is not None:
            df = pd.read_csv(csv_file)
        else:
            df = pd.read_csv("station20250604free.csv")
        
        # 必要な列の存在確認
        required_columns = ['station_name', 'pref_cd']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"都道府県列が見つかりません: {', '.join(missing_columns)}")
            return pd.DataFrame()
        
        # 都道府県名を追加
        df['prefecture'] = df['pref_cd'].map(PREFECTURE_CODE_TO_NAME)
        
        # 路線情報を読み込み
        try:
            route_df = pd.read_csv("eki.csv")
            route_mapping = dict(zip(route_df['路線コード'], route_df['路線名']))
            operator_mapping = dict(zip(route_df['路線コード'], route_df['事業者']))
            
            # 路線名と事業者名をマッピング
            df['route_name'] = df['line_cd'].map(route_mapping).fillna("不明")
            df['operator_name'] = df['line_cd'].map(operator_mapping).fillna("不明")
        except Exception as e:
            st.warning(f"路線データ(eki.csv)の読み込みに失敗しました: {e}")
            df['route_name'] = "不明"
            df['operator_name'] = "不明"
        
        return df
        
    except Exception as e:
        st.error(f"CSVファイルの読み込みでエラーが発生しました: {str(e)}")
        return pd.DataFrame()


def normalize_search_string(text: str, include_katakana: bool = False) -> str:
    """
    検索文字列を正規化（ひらがな・漢字対応、最大20文字）
    
    Args:
        text: 検索文字列
        include_katakana: Trueの場合カタカナも保持、Falseの場合ひらがなに変換
    """
    if not text:
        return ""
    
    if include_katakana:
        # カタカナも保持する場合：ひらがな、カタカナ、漢字を保持
        text = re.sub(r'[^ぁ-んァ-ヾー一-龯]', '', text)
    else:
        # カタカナをひらがなに変換
        text = jaconv.kata2hira(text)
        # ひらがなと漢字のみを保持
        text = re.sub(r'[^ぁ-んー一-龯]', '', text)
    
    # 最大20文字に制限
    return text[:20]


def find_character_positions_cross(df: pd.DataFrame, search_string: str, include_katakana: bool = False) -> Dict:
    """
    複数駅名を使った縦クロスワード検索のため、各文字の位置一致を判定
    """
    if not search_string:
        return {"cross_possible": False, "position_groups": {}, "matching_stations": []}
    
    # 検索文字列の各文字について、その文字を含む駅を位置別に分類
    char_positions = {}
    
    for char_index, char in enumerate(search_string):
        char_positions[char_index] = {}  # 位置別の駅リスト
        
        for _, row in df.iterrows():
            station_name = row['station_name']
            
            # 検索対象の決定
            if include_katakana:
                # カタカナも保持する場合：文字変換を行わない
                search_target = station_name
            else:
                # カタカナをひらがなに変換する場合
                if re.match(r'[ぁ-んー]', char):
                    # ひらがな検索
                    search_target = jaconv.kata2hira(station_name)
                else:
                    # 漢字検索
                    search_target = station_name
            
            # 文字の位置をすべて取得
            for pos in range(len(search_target)):
                if pos < len(search_target) and search_target[pos] == char:
                    if pos not in char_positions[char_index]:
                        char_positions[char_index][pos] = []
                    char_positions[char_index][pos].append(row.to_dict())
    
    # 全文字が同じ位置で見つかる組み合わせを探す
    cross_possible = False
    best_position = None
    matching_stations = []
    
    # 各位置について、全文字が揃うかチェック
    for pos in range(20):  # 最大20文字の駅名を想定
        station_set = []
        valid_position = True
        
        for char_index in range(len(search_string)):
            if pos in char_positions[char_index] and len(char_positions[char_index][pos]) > 0:
                # この位置にこの文字を持つ駅がある
                station_set.append(char_positions[char_index][pos])
            else:
                # この位置にこの文字を持つ駅がない
                valid_position = False
                break
        
        if valid_position and len(station_set) == len(search_string):
            cross_possible = True
            best_position = pos
            # 各文字について1つずつ駅を選択（ランダムに選ぶのではなく最初の駅）
            for char_stations in station_set:
                if char_stations:
                    matching_stations.append(char_stations[0])
            break
    
    return {
        "cross_possible": cross_possible,
        "position": best_position,
        "matching_stations": matching_stations,
        "position_groups": char_positions
    }


def find_character_positions_cross_with_priority(df_all: pd.DataFrame, df_selected: pd.DataFrame, search_string: str, include_katakana: bool = False) -> Dict:
    """
    文字別優先検索を行う縦クロスワード検索関数
    各文字について、選択地域内の駅を優先的に使用し、なければ全国から選択
    該当する全ての駅を返す（全ての位置での組み合わせ）
    """
    if not search_string:
        return {"cross_possible": False, "position_groups": {}, "matching_stations": []}
    
    all_position_results = []
    
    # 各位置について、全文字が揃うかチェック（全位置を調べる）
    for pos in range(20):  # 最大20文字の駅名を想定
        all_matching_stations = []
        all_chars_found = True
        
        for char_index, char in enumerate(search_string):
            char_stations = []
            
            # まず選択地域内で探す（全ての該当駅）
            if not df_selected.empty:
                selected_stations = find_all_chars_at_position(df_selected, char, pos, include_katakana)
                char_stations.extend(selected_stations)
            
            # 選択地域外も含めて全国で探す（重複は後で除去）
            all_stations = find_all_chars_at_position(df_all, char, pos, include_katakana)
            
            # 重複を除去しつつ追加（station_nameとpref_cdで判定）
            existing_keys = {(s['station_name'], s.get('pref_cd', 0)) for s in char_stations}
            for station in all_stations:
                key = (station['station_name'], station.get('pref_cd', 0))
                if key not in existing_keys:
                    char_stations.append(station)
            
            if char_stations:
                all_matching_stations.append((char, char_stations))
            else:
                all_chars_found = False
                break
        
        # この位置で全文字が揃った場合は結果に追加
        if all_chars_found and len(all_matching_stations) == len(search_string):
            all_position_results.append({
                "position": pos,
                "matching_stations": all_matching_stations
            })
    
    # 結果があれば返す
    if all_position_results:
        return {
            "cross_possible": True,
            "all_positions": all_position_results,
            "position_groups": {}
        }
    
    return {"cross_possible": False, "position_groups": {}, "matching_stations": []}


def find_all_chars_at_position(df: pd.DataFrame, char: str, position: int, include_katakana: bool = False) -> List[Dict]:
    """
    指定された位置に指定された文字を持つ全ての駅を探す
    対応文字は元の駅名から取得する
    """
    matching_stations = []
    
    for _, row in df.iterrows():
        station_name = row['station_name']
        
        # 検索対象の決定
        if include_katakana:
            # カタカナも保持する場合：文字変換を行わない
            search_target = station_name
            search_char_normalized = char
        else:
            # カタカナをひらがなに変換する場合
            search_target = jaconv.kata2hira(station_name)
            search_char_normalized = jaconv.kata2hira(char)
        
        # 指定位置に指定文字があるかチェック
        if position < len(search_target) and search_target[position] == search_char_normalized:
            # 結果データに元の駅名の文字を追加
            station_dict = row.to_dict()
            # 対応文字は元の駅名から取得（カタカナならカタカナのまま）
            if position < len(station_name):
                station_dict['actual_char'] = station_name[position]
            else:
                station_dict['actual_char'] = char
            matching_stations.append(station_dict)
    
    return matching_stations


def search_and_analyze_fast(df: pd.DataFrame, search_string: str, selected_prefecture_codes: List[int], hiragana_index: Dict, katakana_index: Dict, include_katakana: bool = False) -> pd.DataFrame:
    """
    インデックスを使用した高速縦クロスワード検索と分析
    """
    if df.empty:
        return pd.DataFrame()
    
    # 検索文字列の正規化
    normalized_search = normalize_search_string(search_string, include_katakana)
    
    if not normalized_search:
        return pd.DataFrame()
    
    # 使用するインデックスを選択
    station_index = katakana_index if include_katakana else hiragana_index
    
    result_rows = []
    
    # 各位置について、縦クロスワードの可能性をチェック
    for pos in range(20):  # 最大20文字の駅名を想定
        # 各文字ごとに該当する駅のリストを取得
        char_station_lists = []
        
        for char_index, char in enumerate(normalized_search):
            # 検索文字を適切に正規化
            if include_katakana:
                search_char = char  # カタカナモードでは変換しない
            else:
                search_char = jaconv.kata2hira(char)  # ひらがなモードではひらがなに変換
            
            # この位置にこの文字を持つ駅を探す
            char_stations = find_stations_by_index(station_index, search_char, pos, df)
            
            # この文字に対応する駅がない場合は、この位置では縦クロスワード不可能
            if not char_stations:
                break
                
            char_station_lists.append(char_stations)
        
        # 全ての文字で駅が見つかった場合のみ結果に追加
        if len(char_station_lists) == len(normalized_search):
            # 各文字ごとに駅を結果に追加
            for char_index, stations_for_char in enumerate(char_station_lists):
                for station_data in stations_for_char:
                    # 検索範囲を決定
                    station_pref_cd = station_data.get('pref_cd', 0)
                    if selected_prefecture_codes and station_pref_cd in selected_prefecture_codes:
                        search_scope = '🔵 選択地域内'
                    else:
                        search_scope = '🔴 全国'
                    
                    # 対応文字は元の駅名から実際に取得
                    station_name = station_data.get('station_name', '')
                    if pos < len(station_name):
                        actual_char = station_name[pos]
                    else:
                        actual_char = normalized_search[char_index]
                    
                    result_rows.append({
                        'station_name': station_data['station_name'],
                        'prefecture': station_data.get('prefecture', '不明'),
                        'operator_name': station_data.get('operator_name', '不明'),
                        'route_name': station_data.get('route_name', '不明'),
                        'search_char': actual_char,
                        'char_position': pos + 1,  # 1ベースに変換
                        'search_scope': search_scope
                    })
    
    return pd.DataFrame(result_rows)


def search_and_analyze(df: pd.DataFrame, search_string: str, selected_prefecture_codes: List[int], include_katakana: bool = False) -> pd.DataFrame:
    """
    複数駅名を使った縦クロスワード検索と分析（文字別優先順位付き）
    """
    if df.empty:
        return pd.DataFrame()
    
    # 検索文字列の正規化
    normalized_search = normalize_search_string(search_string, include_katakana)
    
    if not normalized_search:
        # 検索文字列が空の場合は空を返す
        return pd.DataFrame()
    
    # 選択地域のデータと全国データを準備
    if selected_prefecture_codes:
        df_selected = df[df['pref_cd'].isin(selected_prefecture_codes)].copy()
    else:
        df_selected = pd.DataFrame()
    
    # 文字別優先検索を実行
    cross_info = find_character_positions_cross_with_priority(df, df_selected, normalized_search, include_katakana)
    
    if cross_info['cross_possible'] and cross_info.get('all_positions'):
        # マッチした駅の情報を整理（複数位置・複数駅を展開）
        result_rows = []
        
        for position_result in cross_info['all_positions']:
            position = position_result['position']
            matching_stations = position_result['matching_stations']
            
            for char_index, (char, stations_list) in enumerate(matching_stations):
                for station_data in stations_list:
                    # 検索範囲を決定（絵文字付き）
                    station_pref_cd = station_data.get('pref_cd', 0)
                    if selected_prefecture_codes and station_pref_cd in selected_prefecture_codes:
                        search_scope = '🔵 選択地域内'
                    else:
                        search_scope = '🔴 全国'
                    
                    # 対応文字は元の駅名から取得（actual_charがあればそれを使用）
                    display_char = station_data.get('actual_char', char)
                    
                    result_rows.append({
                        'station_name': station_data['station_name'],
                        'prefecture': station_data['prefecture'],
                        'operator_name': station_data['operator_name'],
                        'route_name': station_data['route_name'],
                        'search_char': display_char,
                        'char_position': position + 1,  # 1ベースに変換
                        'search_scope': search_scope
                    })
        
        return pd.DataFrame(result_rows)
    else:
        return pd.DataFrame()


def style_dataframe(df):
    """
    データフレームに選択地域の背景色スタイルと境界線スタイルを適用
    """
    def highlight_selected_region(row):
        if '🔵 選択地域内' in str(row.get('search_scope', '')):
            return ['background-color: #e3f2fd; border: 2px solid #1976d2'] * len(row)  # 薄い青色 + 濃い青の境界線
        else:
            return ['background-color: #fff3e0; border: 2px solid #f57c00'] * len(row)  # 薄いオレンジ色 + オレンジの境界線
    
    styled_df = df.style.apply(highlight_selected_region, axis=1)
    
    # セル間の境界線を太くするCSS
    styled_df = styled_df.set_table_styles([
        {
            'selector': 'td',
            'props': [
                ('border', '2px solid #ddd'),
                ('border-collapse', 'separate'),
                ('border-spacing', '0'),
                ('padding', '8px')
            ]
        },
        {
            'selector': 'th',
            'props': [
                ('border', '3px solid #333'),
                ('background-color', '#f5f5f5'),
                ('font-weight', 'bold'),
                ('padding', '10px')
            ]
        },
        {
            'selector': 'table',
            'props': [
                ('border-collapse', 'separate'),
                ('border-spacing', '2px')
            ]
        }
    ])
    
    return styled_df


def create_download_csv(df: pd.DataFrame) -> str:
    """
    ダウンロード用のCSV文字列を生成
    """
    if df.empty:
        return ""
    
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8')
    return output.getvalue()


def main():
    st.title("駅名縦クロスワード検索ツール")
    
    # データソースの表示
    st.markdown("📊 **データソース**: [駅データ.jp（ekidata.jp）](https://ekidata.jp/) のデータを使用")
    
    # 全般的な注意書き
    st.warning("""
    ⚠️ **重要な注意事項**
    - 検索結果通りに駅名が印字されるとは限りません。
    - 鉄道会社によって、印字の方法が異なる場合があります。
    """)
    
    # インデックスファイルの読み込み試行
    hiragana_index, katakana_index, indexed_df = load_precomputed_index()
    use_fast_search = hiragana_index is not None
    
    if use_fast_search:
        st.success("高速インデックスを使用します")
    else:
        st.info("💡 高速化のため create_index.py を実行してインデックスを作成してください")
    
    # カスタムCSS for 検索範囲の視覚的区別
    st.markdown("""
    <style>
    /* データフレーム全体のスタイリング */
    .stDataFrame {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* テーブルのボーダーを強調 */
    .stDataFrame table {
        border-collapse: separate !important;
        border-spacing: 2px !important;
        border: 3px solid #333 !important;
    }
    
    /* セルのボーダーを太く */
    .stDataFrame td, .stDataFrame th {
        border: 2px solid #666 !important;
        padding: 8px !important;
    }
    
    /* ヘッダーのスタイリング */
    .stDataFrame th {
        background-color: #f0f0f0 !important;
        font-weight: bold !important;
        border: 3px solid #333 !important;
    }
    
    /* 検索範囲列のスタイリング */
    div[data-testid="column"] div[data-testid="stDataFrame"] td:last-child {
        font-weight: bold;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # セッション状態の初期化
    if 'search_results' not in st.session_state:
        st.session_state.search_results = pd.DataFrame()
    
    # CSVファイルアップロード（展開可能）
    with st.expander("📁 CSVファイルアップロード（オプション）"):
        st.info("💡 駅データ.jp（ekidata.jp）のデータを使用しています")
        uploaded_file = st.file_uploader(
            "最新データを使用する場合は選択してください", 
            type=['csv'],
            help="省略した場合はデフォルトの駅データを使用します"
        )
    
    # データ読み込み
    if use_fast_search and uploaded_file is None:
        # インデックス使用時は事前処理済みデータを使用
        df = indexed_df.copy()
        # 必要な列が不足している場合は補完
        if 'prefecture' not in df.columns:
            df['prefecture'] = df['pref_cd'].map(PREFECTURE_CODE_TO_NAME)
        if 'route_name' not in df.columns:
            df['route_name'] = "不明"
        if 'operator_name' not in df.columns:
            df['operator_name'] = "不明"
    else:
        # 通常のデータ読み込み
        if uploaded_file is not None:
            df = load_station_data(uploaded_file)
        else:
            df = load_station_data()
    
    if df.empty:
        st.warning("データが読み込まれていません。")
        return
    
    st.success(f"データ読み込み完了: {len(df):,} 件の駅データ")
    
    # 検索文字列入力
    st.subheader("1. 検索文字列入力")
    search_input = st.text_input(
        "検索文字列を入力してください（ひらがな・漢字対応、最大20文字）",
        max_chars=20,
        help="複数駅名で縦クロスワードを検索）"
    )
    
    # カタカナ処理の切り替え
    include_katakana = st.checkbox(
        "カタカナを別文字として扱う",
        value=False,
        help="オン: カタカナをそのまま検索対象とする（「あ」と「ア」を別文字扱い）\nオフ: カタカナをひらがなに変換して検索（「あ」と「ア」を同じ文字扱い）"
    )

    
    # 都道府県・地方選択
    st.subheader("2. 地方・都道府県選択")
    
    # 地方区分と都道府県のオプションを取得
    prefecture_options = get_prefecture_options()
    
    selected_options = st.multiselect(
        "検索対象とする地方・都道府県を選択してください（複数選択可、未選択時は全国対象）",
        options=prefecture_options,
        default=[],
        help="【地方名】を選択すると該当地方の全都道府県が対象になります。\n個別の都道府県も選択可能です。"
    )
    
    # 選択されたオプションから都道府県コードを取得
    selected_prefecture_codes = get_selected_prefecture_codes(selected_options)
    
    if selected_options:
        selected_pref_names = [PREFECTURE_CODE_TO_NAME[code] for code in selected_prefecture_codes if code in PREFECTURE_CODE_TO_NAME]
        st.info(f"選択中の都道府県: {', '.join(selected_pref_names)}")
    
    # 検索実行
    if st.button("検索実行", type="primary") or search_input or selected_options != st.session_state.get('prev_selected', []):
        st.session_state.prev_selected = selected_options
        
        with st.spinner('検索中...'):
            # 高速検索かどうかで処理を分岐
            if use_fast_search and uploaded_file is None:
                results = search_and_analyze_fast(df, search_input, selected_prefecture_codes, hiragana_index, katakana_index, include_katakana)
            else:
                results = search_and_analyze(df, search_input, selected_prefecture_codes, include_katakana)
            st.session_state.search_results = results
    
    # 検索結果表示
    results = st.session_state.search_results
    
    st.subheader("3. 検索結果")
    
    if not results.empty:
        st.success(f"クロスワード検索可能: {len(results):,} 駅でパターン発見")
        
        # 選択中の都道府県を表示（既に上部で表示済みのため削除）
        
        # 検索文字列を表示
        if search_input:
            normalized = normalize_search_string(search_input, include_katakana)
            if normalized:
                katakana_mode = "カタカナ別文字扱い" if include_katakana else "カタカナ→ひらがな変換"
                st.info(f"検索文字列: {normalized} （{katakana_mode}）")
        
        # 結果テーブル表示（位置別にグループ化）
        if 'char_position' in results.columns:
            # 凡例表示
            st.markdown("""
            **📋 色分け凡例**
            - <span style="background-color: #e3f2fd; padding: 2px 8px; border-radius: 3px;">🔵 選択地域内</span>
            - <span style="background-color: #fff3e0; padding: 2px 8px; border-radius: 3px;">🔴 全国</span>
            
            """, unsafe_allow_html=True)
            
            positions = sorted(results['char_position'].unique())
            
            for pos in positions:
                st.subheader(f"📍 {pos}文字目での組み合わせ")
                pos_results = results[results['char_position'] == pos]
                
                st.dataframe(
                    style_dataframe(pos_results),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "station_name": "駅名",
                        "prefecture": "都道府県",
                        "operator_name": "事業者",
                        "route_name": "路線名",
                        "search_char": "対応文字",
                        "char_position": st.column_config.NumberColumn("文字位置", format="%d"),
                        "search_scope": st.column_config.TextColumn(
                            "検索範囲",
                            help="🔵 選択地域内 / 🔴 全国"
                        )
                    }
                )
                
                # 選択地域内の駅数を表示
                selected_count = len(pos_results[pos_results['search_scope'] == '🔵 選択地域内'])
                total_count = len(pos_results)
                if selected_count > 0:
                    st.success(f"🔵 選択地域内: {selected_count}駅 / 全体: {total_count}駅")
        else:
            # 位置情報がない場合は従来通り表示
            st.dataframe(
                style_dataframe(results),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "station_name": "駅名",
                    "prefecture": "都道府県",
                    "operator_name": "事業者",
                    "route_name": "路線名",
                    "search_char": "対応文字",
                    "char_position": st.column_config.NumberColumn("文字位置", format="%d"),
                    "search_scope": st.column_config.TextColumn(
                        "検索範囲",
                        help="🔵 選択地域内 / 🔴 全国"
                    )
                }
            )
        
        # CSVダウンロード
        st.subheader("4. CSVダウンロード")
        csv_data = create_download_csv(results)
        
        if csv_data:
            st.download_button(
                label="検索結果をCSVでダウンロード",
                data=csv_data,
                file_name=f"station_search_results_{len(results)}件.csv",
                mime="text/csv",
                type="secondary"
            )
    else:
        if search_input or selected_options:
            st.warning("指定条件で縦クロスワードが検索できません")
            st.info("💡 ヒント: 検索文字列の各文字が同じ位置（何文字目）にある駅の組み合わせが必要です")
        else:
            st.info("検索文字列を入力して縦クロスワードを検索してください")


if __name__ == "__main__":
    main()
