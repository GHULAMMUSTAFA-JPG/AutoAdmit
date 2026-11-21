"""Live University Discovery Engine via Wikidata SPARQL API and Dynamic Domain Validation."""

from datetime import datetime, timezone
import json
import os
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse
import httpx

from src.config import settings
from src.core.logger import setup_logger
from src.core.policies import concurrency_controller, policy_manager
from src.core.telemetry import (
    ConfidenceLevel,
    ErrorCode,
    JobScorecard,
    StepResult,
    TerminalStatus,
    phase1_logger,
)
from src.models.university import (
    DepartmentEndpoint,
    FacultyRosterEndpoint,
    FeasibilityTier,
    PreRunCostEstimate,
    ScholarshipType,
    University,
    UniversityDepartmentCache,
)
from src.services.search_provider import (
    DISCIPLINE_SYNONYMS,
    FACULTY_ROSTER_MARKERS,
    normalize_discipline_key,
    search_provider,
)

logger = setup_logger("DiscoveryService")

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_USER_AGENT = getattr(
    settings,
    "WIKIMEDIA_USER_AGENT",
    "AutoAdmitEngine/1.0 (https://github.com/autoadmit/engine; autoadmit-research@users.noreply.github.com) python-httpx"
)

# Comprehensive province and city keywords mapping for accurate regional filtering
PROVINCE_LOCATION_KEYWORDS: Dict[str, List[str]] = {
    "Sichuan": ["sichuan", "chengdu", "mianyang", "nanchong", "zigong", "yibin", "luzhou", "deyang", "四川", "成都", "绵阳", "南充", "自贡", "宜宾", "cdut", "uestc", "swjtu", "scu", "swpu"],
    "Beijing": ["beijing", "peking", "tsinghua", "beihang", "bupt", "bit", "ruc", "ucas", "北京", "清华", "北大", "北航", "北邮"],
    "Shanghai": ["shanghai", "fudan", "tongji", "sjtu", "ecnu", "上海", "复旦", "同济", "交大"],
    "Guangdong": ["guangdong", "guangzhou", "shenzhen", "zhuhai", "foshan", "dongguan", "广东", "广州", "深圳", "珠海", "sysu", "scut", "sustech"],
    "Jiangsu": ["jiangsu", "nanjing", "suzhou", "wuxi", "xuzhou", "changzhou", "zhenjiang", "江苏", "南京", "苏州", "无锡", "徐州", "nju", "seu", "nuaa", "nust", "nuist"],
    "Zhejiang": ["zhejiang", "hangzhou", "ningbo", "wenzhou", "shaoxing", "jinhua", "浙江", "杭州", "宁波", "温州", "zju", "hdu"],
    "Hubei": ["hubei", "wuhan", "yichang", "xiangyang", "湖北", "武汉", "hust", "whu"],
    "Shaanxi": ["shaanxi", "xi'an", "xian", "xianyang", "yan'an", "陕西", "西安", "咸阳", "xjtu", "xidian", "nwpu"],
    "Heilongjiang": ["heilongjiang", "harbin", "daqing", "qiqihar", "黑龙江", "哈尔滨", "hit", "heu"],
    "Shandong": ["shandong", "jinan", "qingdao", "weihai", "yantai", "山东", "济南", "青岛", "威海", "sdu", "ouc", "upc"],
    "Hunan": ["hunan", "changsha", "xiangtan", "zhuzhou", "湖南", "长沙", "湘潭", "csu", "hnu"],
    "Anhui": ["anhui", "hefei", "wuhu", "bengbu", "安徽", "合肥", "芜湖", "ustc", "hfut"],
    "Tianjin": ["tianjin", "天津", "nankai", "tju"],
    "Chongqing": ["chongqing", "重庆", "cqu", "cqupt"],
    "Henan": ["henan", "zhengzhou", "kaifeng", "luoyang", "河南", "郑州", "开封", "zzu"],
    "Fujian": ["fujian", "xiamen", "fuzhou", "quanzhou", "福建", "厦门", "福州", "xmu"],
    "Liaoning": ["liaoning", "shenyang", "dalian", "辽宁", "沈阳", "大连", "neu", "dlut"],
    "Jilin": ["jilin", "changchun", "吉林", "长春", "jlu"],
    "Gansu": ["gansu", "lanzhou", "甘肃", "兰州", "lzu"],
    "Guangxi": ["guangxi", "nanning", "guilin", "广西", "南宁", "桂林"],
    "Yunnan": ["yunnan", "kunming", "云南", "昆明", "ynu"],
    "Jiangxi": ["jiangxi", "nanchang", "江西", "南昌", "ncu"],
    "Shanxi": ["shanxi", "taiyuan", "山西", "太原", "tyut"],
    "Xinjiang": ["xinjiang", "urumqi", "新疆", "乌鲁木齐", "xju"],
}


def _clean_domain(url_str: Optional[str]) -> Optional[str]:
    if not url_str:
        return None
    try:
        raw = url_str.strip()
        if not raw.startswith("http://") and not raw.startswith("https://"):
            raw = "http://" + raw
        p = urlparse(raw)
        netloc = p.netloc.lower().split(":")[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        # Normalize any subdomain (e.g. en.bjtu.edu.cn, ar.shisu.edu.cn) to its 3-part registrable root (bjtu.edu.cn, shisu.edu.cn)
        if netloc.endswith(".edu.cn") or netloc.endswith(".ac.cn"):
            parts = [pt for pt in netloc.split(".") if pt]
            if len(parts) > 3:
                netloc = ".".join(parts[-3:])
        return netloc if netloc else None
    except Exception:
        return None


# Official Ministry of Education (MOE) Project 985 & Project 211 Domain Registries
PROJECT_985_DOMAINS = {
    "tsinghua.edu.cn", "pku.edu.cn", "zju.edu.cn", "fudan.edu.cn", "sjtu.edu.cn",
    "ustc.edu.cn", "nju.edu.cn", "hit.edu.cn", "xjtu.edu.cn", "ruc.edu.cn",
    "bit.edu.cn", "tongji.edu.cn", "seu.edu.cn", "scu.edu.cn", "nankai.edu.cn",
    "tju.edu.cn", "bnu.edu.cn", "cau.edu.cn", "muc.edu.cn",
    "hust.edu.cn", "whu.edu.cn", "csu.edu.cn", "hnu.edu.cn", "sysu.edu.cn",
    "scut.edu.cn", "cqu.edu.cn", "uestc.edu.cn", "nwpu.edu.cn", "dlut.edu.cn",
    "neu.edu.cn", "jlu.edu.cn", "sdu.edu.cn", "ouc.edu.cn", "xmu.edu.cn",
    "lzu.edu.cn", "nwsuaf.edu.cn", "cug.edu.cn", "ecnu.edu.cn"
}

PROJECT_211_DOMAINS = {
    "buaa.edu.cn", "bupt.edu.cn", "xidian.edu.cn", "nuaa.edu.cn", "nust.edu.cn",
    "bjtu.edu.cn", "ustb.edu.cn", "buct.edu.cn", "bfsu.edu.cn", "uibe.edu.cn",
    "cufe.edu.cn", "shisu.edu.cn", "shufe.edu.cn", "swufe.edu.cn", "swjtu.edu.cn",
    "swpu.edu.cn", "cdut.edu.cn", "hebut.edu.cn", "tyut.edu.cn", "imnu.edu.cn",
    "dhu.edu.cn", "ecust.edu.cn", "shu.edu.cn", "suda.edu.cn", "jiangnan.edu.cn",
    "cumt.edu.cn", "hhu.edu.cn", "njau.edu.cn", "njnu.edu.cn", "cpu.edu.cn",
    "hfut.edu.cn", "ahu.edu.cn", "fzu.edu.cn", "ncu.edu.cn", "zzu.edu.cn",
    "whut.edu.cn", "ccnu.edu.cn", "hzau.edu.cn", "zuel.edu.cn", "hunnu.edu.cn",
    "jnu.edu.cn", "scnu.edu.cn", "gxu.edu.cn", "hainanu.edu.cn", "swu.edu.cn",
    "sicau.edu.cn", "gzu.edu.cn", "ynu.edu.cn", "nwu.edu.cn", "snnu.edu.cn",
    "chd.edu.cn", "xju.edu.cn", "shzu.edu.cn", "hrbeu.edu.cn", "nefu.edu.cn",
    "neau.edu.cn", "dlmu.edu.cn", "lnu.edu.cn", "ybu.edu.cn", "nenu.edu.cn"
}

# Universities verified to waive application fees (0 RMB) for CSC / International Master's
FEE_WAIVED_DOMAINS = {
    "nuist.edu.cn", "uestc.edu.cn", "whut.edu.cn", "dlut.edu.cn",
    "nwpu.edu.cn", "lzu.edu.cn", "just.edu.cn", "ujs.edu.cn", "ctgu.edu.cn"
}

# Static Subject-Wise Ranking Table (CSRankings / Shanghai GRAS Baseline for CS, AI, SE, EE)
SUBJECT_RANKINGS_TABLE: Dict[str, Dict[str, int]] = {
    "tsinghua.edu.cn": {"cs": 1, "ai": 1, "se": 1, "ee": 1},
    "pku.edu.cn": {"cs": 2, "ai": 2, "se": 2, "ee": 3},
    "zju.edu.cn": {"cs": 3, "ai": 3, "se": 3, "ee": 4},
    "sjtu.edu.cn": {"cs": 4, "ai": 4, "se": 5, "ee": 2},
    "nju.edu.cn": {"cs": 5, "ai": 5, "se": 4, "ee": 12},
    "fudan.edu.cn": {"cs": 6, "ai": 6, "se": 8, "ee": 9},
    "ustc.edu.cn": {"cs": 7, "ai": 7, "se": 9, "ee": 6},
    "hit.edu.cn": {"cs": 8, "ai": 8, "se": 6, "ee": 7},
    "buaa.edu.cn": {"cs": 9, "ai": 10, "se": 7, "ee": 8},
    "hust.edu.cn": {"cs": 10, "ai": 11, "se": 11, "ee": 5},
    "uestc.edu.cn": {"cs": 11, "ai": 12, "se": 12, "ee": 3},
    "bit.edu.cn": {"cs": 12, "ai": 13, "se": 14, "ee": 10},
    "whu.edu.cn": {"cs": 13, "ai": 15, "se": 10, "ee": 15},
    "xjtu.edu.cn": {"cs": 14, "ai": 14, "se": 16, "ee": 6},
    "xidian.edu.cn": {"cs": 15, "ai": 16, "se": 15, "ee": 4},
    "bupt.edu.cn": {"cs": 16, "ai": 17, "se": 17, "ee": 5},
    "nwpu.edu.cn": {"cs": 17, "ai": 18, "se": 13, "ee": 11},
    "sysu.edu.cn": {"cs": 18, "ai": 19, "se": 18, "ee": 16},
    "seu.edu.cn": {"cs": 19, "ai": 20, "se": 19, "ee": 7},
    "tongji.edu.cn": {"cs": 20, "ai": 21, "se": 20, "ee": 18},
    "tju.edu.cn": {"cs": 21, "ai": 22, "se": 21, "ee": 17},
    "nankai.edu.cn": {"cs": 22, "ai": 23, "se": 22, "ee": 24},
    "scu.edu.cn": {"cs": 23, "ai": 24, "se": 23, "ee": 20},
    "sdu.edu.cn": {"cs": 24, "ai": 25, "se": 24, "ee": 22},
    "csu.edu.cn": {"cs": 25, "ai": 26, "se": 25, "ee": 21},
    "dlut.edu.cn": {"cs": 26, "ai": 27, "se": 26, "ee": 23},
    "neu.edu.cn": {"cs": 27, "ai": 28, "se": 27, "ee": 25},
    "jlu.edu.cn": {"cs": 28, "ai": 29, "se": 28, "ee": 27},
    "xmu.edu.cn": {"cs": 29, "ai": 30, "se": 29, "ee": 28},
    "scut.edu.cn": {"cs": 30, "ai": 31, "se": 30, "ee": 19},
    "nuaa.edu.cn": {"cs": 32, "ai": 33, "se": 31, "ee": 26},
    "nust.edu.cn": {"cs": 34, "ai": 34, "se": 35, "ee": 29},
    "hdu.edu.cn": {"cs": 38, "ai": 40, "se": 38, "ee": 32},
    "nuist.edu.cn": {"cs": 42, "ai": 44, "se": 43, "ee": 40},
}

# Non-Master's 3-year vocational / junior / adult college exclusion markers
VOCATIONAL_EXCLUSION_ZH = ("职业", "专科", "技师", "成人", "广播电视", "开放大学", "职工", "干部", "卫校", "幼师")
VOCATIONAL_EXCLUSION_EN = ("vocational", "junior college", "technical college", "adult", "open university", "radio and tv")

# Official China MOE / CHSI Graduate Admissions (硕士点高校) Core Registry for Triple-Check & MOE Mode
MOE_MASTERS_REGISTRY = [
    ("Tsinghua University", "清华大学", "tsinghua.edu.cn", "Beijing"),
    ("Peking University", "北京大学", "pku.edu.cn", "Beijing"),
    ("Beihang University", "北京航空航天大学", "buaa.edu.cn", "Beijing"),
    ("Beijing Institute of Technology", "北京理工大学", "bit.edu.cn", "Beijing"),
    ("Beijing University of Posts and Telecommunications", "北京邮电大学", "bupt.edu.cn", "Beijing"),
    ("University of Chinese Academy of Sciences", "中国科学院大学", "ucas.ac.cn", "Beijing"),
    ("Renmin University of China", "中国人民大学", "ruc.edu.cn", "Beijing"),
    ("Beijing Normal University", "北京师范大学", "bnu.edu.cn", "Beijing"),
    ("Beijing Jiaotong University", "北京交通大学", "bjtu.edu.cn", "Beijing"),
    ("University of Science and Technology Beijing", "北京科技大学", "ustb.edu.cn", "Beijing"),
    ("Beijing University of Chemical Technology", "北京化工大学", "buct.edu.cn", "Beijing"),
    ("Beijing University of Technology", "北京工业大学", "bjut.edu.cn", "Beijing"),
    ("North China Electric Power University", "华北电力大学", "ncepu.edu.cn", "Beijing"),
    ("China Agricultural University", "中国农业大学", "cau.edu.cn", "Beijing"),
    ("Minzu University of China", "中央民族大学", "muc.edu.cn", "Beijing"),
    ("Capital Normal University", "首都师范大学", "cnu.edu.cn", "Beijing"),
    ("Beijing Information Science and Technology University", "北京信息科技大学", "bistu.edu.cn", "Beijing"),
    ("Fudan University", "复旦大学", "fudan.edu.cn", "Shanghai"),
    ("Shanghai Jiao Tong University", "上海交通大学", "sjtu.edu.cn", "Shanghai"),
    ("Tongji University", "同济大学", "tongji.edu.cn", "Shanghai"),
    ("East China Normal University", "华东师范大学", "ecnu.edu.cn", "Shanghai"),
    ("East China University of Science and Technology", "华东理工大学", "ecust.edu.cn", "Shanghai"),
    ("Shanghai University", "上海大学", "shu.edu.cn", "Shanghai"),
    ("Donghua University", "东华大学", "dhu.edu.cn", "Shanghai"),
    ("University of Shanghai for Science and Technology", "上海理工大学", "usst.edu.cn", "Shanghai"),
    ("ShanghaiTech University", "上海科技大学", "shanghaitech.edu.cn", "Shanghai"),
    ("Shanghai Maritime University", "上海海事大学", "shmtu.edu.cn", "Shanghai"),
    ("Shanghai Normal University", "上海师范大学", "shnu.edu.cn", "Shanghai"),
    ("Zhejiang University", "浙江大学", "zju.edu.cn", "Zhejiang"),
    ("Hangzhou Dianzi University", "杭州电子科技大学", "hdu.edu.cn", "Zhejiang"),
    ("Zhejiang University of Technology", "浙江工业大学", "zjut.edu.cn", "Zhejiang"),
    ("Zhejiang Normal University", "浙江师范大学", "zjnu.edu.cn", "Zhejiang"),
    ("Ningbo University", "宁波大学", "nbu.edu.cn", "Zhejiang"),
    ("Zhejiang Sci-Tech University", "浙江理工大学", "zstu.edu.cn", "Zhejiang"),
    ("China Jiliang University", "中国计量大学", "cjlu.edu.cn", "Zhejiang"),
    ("Hangzhou Normal University", "杭州师范大学", "hznu.edu.cn", "Zhejiang"),
    ("Wenzhou University", "温州大学", "wzu.edu.cn", "Zhejiang"),
    ("Nanjing University", "南京大学", "nju.edu.cn", "Jiangsu"),
    ("Southeast University", "东南大学", "seu.edu.cn", "Jiangsu"),
    ("Nanjing University of Aeronautics and Astronautics", "南京航空航天大学", "nuaa.edu.cn", "Jiangsu"),
    ("Nanjing University of Science and Technology", "南京理工大学", "nust.edu.cn", "Jiangsu"),
    ("Nanjing University of Information Science and Technology", "南京信息工程大学", "nuist.edu.cn", "Jiangsu"),
    ("Nanjing University of Posts and Telecommunications", "南京邮电大学", "njupt.edu.cn", "Jiangsu"),
    ("Soochow University", "苏州大学", "suda.edu.cn", "Jiangsu"),
    ("Jiangnan University", "江南大学", "jiangnan.edu.cn", "Jiangsu"),
    ("China University of Mining and Technology", "中国矿业大学", "cumt.edu.cn", "Jiangsu"),
    ("Hohai University", "河海大学", "hhu.edu.cn", "Jiangsu"),
    ("Jiangsu University", "江苏大学", "ujs.edu.cn", "Jiangsu"),
    ("Jiangsu University of Science and Technology", "江苏科技大学", "just.edu.cn", "Jiangsu"),
    ("Nanjing Tech University", "南京工业大学", "njtech.edu.cn", "Jiangsu"),
    ("Nanjing Normal University", "南京师范大学", "njnu.edu.cn", "Jiangsu"),
    ("Yangzhou University", "扬州大学", "yzu.edu.cn", "Jiangsu"),
    ("Wuhan University", "武汉大学", "whu.edu.cn", "Hubei"),
    ("Huazhong University of Science and Technology", "华中科技大学", "hust.edu.cn", "Hubei"),
    ("Wuhan University of Technology", "武汉理工大学", "whut.edu.cn", "Hubei"),
    ("China University of Geosciences (Wuhan)", "中国地质大学(武汉)", "cug.edu.cn", "Hubei"),
    ("Central China Normal University", "华中师范大学", "ccnu.edu.cn", "Hubei"),
    ("Huazhong Agricultural University", "华中农业大学", "hzau.edu.cn", "Hubei"),
    ("Wuhan University of Science and Technology", "武汉科技大学", "wust.edu.cn", "Hubei"),
    ("Hubei University", "湖北大学", "hubu.edu.cn", "Hubei"),
    ("Hubei University of Technology", "湖北工业大学", "hbut.edu.cn", "Hubei"),
    ("Wuhan Institute of Technology", "武汉工程大学", "wit.edu.cn", "Hubei"),
    ("Wuhan Textile University", "武汉纺织大学", "wtu.edu.cn", "Hubei"),
    ("Wuhan Polytechnic University", "武汉轻工大学", "whpu.edu.cn", "Hubei"),
    ("China Three Gorges University", "三峡大学", "ctgu.edu.cn", "Hubei"),
    ("Yangtze University", "长江大学", "yangtzeu.edu.cn", "Hubei"),
    ("South-Central Minzu University", "中南民族大学", "scuec.edu.cn", "Hubei"),
    ("Sichuan University", "四川大学", "scu.edu.cn", "Sichuan"),
    ("University of Electronic Science and Technology of China", "电子科技大学", "uestc.edu.cn", "Sichuan"),
    ("Southwest Jiaotong University", "西南交通大学", "swjtu.edu.cn", "Sichuan"),
    ("Southwestern University of Finance and Economics", "西南财经大学", "swufe.edu.cn", "Sichuan"),
    ("Chengdu University of Technology", "成都理工大学", "cdut.edu.cn", "Sichuan"),
    ("Southwest Petroleum University", "西南石油大学", "swpu.edu.cn", "Sichuan"),
    ("Sichuan Agricultural University", "四川农业大学", "sicau.edu.cn", "Sichuan"),
    ("Southwest University of Science and Technology", "西南科技大学", "swust.edu.cn", "Sichuan"),
    ("Chengdu University of Information Technology", "成都信息工程大学", "cuit.edu.cn", "Sichuan"),
    ("Sichuan Normal University", "四川师范大学", "sicnu.edu.cn", "Sichuan"),
    ("Xihua University", "西华大学", "xhu.edu.cn", "Sichuan"),
    ("Chengdu University", "成都大学", "cdu.edu.cn", "Sichuan"),
    ("China West Normal University", "西华师范大学", "cwnu.edu.cn", "Sichuan"),
    ("Sichuan University of Science and Engineering", "四川轻化工大学", "suse.edu.cn", "Sichuan"),
    ("Southwest Minzu University", "西南民族大学", "swun.edu.cn", "Sichuan"),
    ("Xi'an Jiaotong University", "西安交通大学", "xjtu.edu.cn", "Shaanxi"),
    ("Northwestern Polytechnical University", "西北工业大学", "nwpu.edu.cn", "Shaanxi"),
    ("Xidian University", "西安电子科技大学", "xidian.edu.cn", "Shaanxi"),
    ("Northwest University", "西北大学", "nwu.edu.cn", "Shaanxi"),
    ("Shaanxi Normal University", "陕西师范大学", "snnu.edu.cn", "Shaanxi"),
    ("Chang'an University", "长安大学", "chd.edu.cn", "Shaanxi"),
    ("Northwest A&F University", "西北农林科技大学", "nwsuaf.edu.cn", "Shaanxi"),
    ("Xi'an University of Technology", "西安理工大学", "xaut.edu.cn", "Shaanxi"),
    ("Xi'an University of Architecture and Technology", "西安建筑科技大学", "xauat.edu.cn", "Shaanxi"),
    ("Shaanxi University of Science and Technology", "陕西科技大学", "sust.edu.cn", "Shaanxi"),
    ("Xi'an University of Posts and Telecommunications", "西安邮电大学", "xupt.edu.cn", "Shaanxi"),
    ("Xi'an Technological University", "西安工业大学", "xatu.edu.cn", "Shaanxi"),
    ("Xi'an University of Science and Technology", "西安科技大学", "xust.edu.cn", "Shaanxi"),
    ("Sun Yat-sen University", "中山大学", "sysu.edu.cn", "Guangdong"),
    ("South China University of Technology", "华南理工大学", "scut.edu.cn", "Guangdong"),
    ("Southern University of Science and Technology", "南方科技大学", "sustech.edu.cn", "Guangdong"),
    ("Jinan University", "暨南大学", "jnu.edu.cn", "Guangdong"),
    ("South China Normal University", "华南师范大学", "scnu.edu.cn", "Guangdong"),
    ("Shenzhen University", "深圳大学", "szu.edu.cn", "Guangdong"),
    ("Guangdong University of Technology", "广东工业大学", "gdut.edu.cn", "Guangdong"),
    ("South China Agricultural University", "华南农业大学", "scau.edu.cn", "Guangdong"),
    ("Guangzhou University", "广州大学", "gzhu.edu.cn", "Guangdong"),
    ("Shantou University", "汕头大学", "stu.edu.cn", "Guangdong"),
    ("Dongguan University of Technology", "东莞理工学院", "dgut.edu.cn", "Guangdong"),
    ("Foshan University", "佛山大学", "fosu.edu.cn", "Guangdong"),
    ("Harbin Institute of Technology", "哈尔滨工业大学", "hit.edu.cn", "Heilongjiang"),
    ("Harbin Engineering University", "哈尔滨工程大学", "hrbeu.edu.cn", "Heilongjiang"),
    ("Northeast Forestry University", "东北林业大学", "nefu.edu.cn", "Heilongjiang"),
    ("Northeast Agricultural University", "东北农业大学", "neau.edu.cn", "Heilongjiang"),
    ("Harbin University of Science and Technology", "哈尔滨理工大学", "hrbust.edu.cn", "Heilongjiang"),
    ("Heilongjiang University", "黑龙江大学", "hlju.edu.cn", "Heilongjiang"),
    ("Northeast Petroleum University", "东北石油大学", "nepu.edu.cn", "Heilongjiang"),
    ("Shandong University", "山东大学", "sdu.edu.cn", "Shandong"),
    ("Ocean University of China", "中国海洋大学", "ouc.edu.cn", "Shandong"),
    ("China University of Petroleum (East China)", "中国石油大学(华东)", "upc.edu.cn", "Shandong"),
    ("Shandong Normal University", "山东师范大学", "sdnu.edu.cn", "Shandong"),
    ("Shandong University of Science and Technology", "山东科技大学", "sdust.edu.cn", "Shandong"),
    ("Qingdao University", "青岛大学", "qdu.edu.cn", "Shandong"),
    ("Qingdao University of Science and Technology", "青岛科技大学", "qust.edu.cn", "Shandong"),
    ("University of Jinan", "济南大学", "ujn.edu.cn", "Shandong"),
    ("Qilu University of Technology", "齐鲁工业大学", "qlu.edu.cn", "Shandong"),
    ("Central South University", "中南大学", "csu.edu.cn", "Hunan"),
    ("Hunan University", "湖南大学", "hnu.edu.cn", "Hunan"),
    ("Hunan Normal University", "湖南师范大学", "hunnu.edu.cn", "Hunan"),
    ("Xiangtan University", "湘潭大学", "xtu.edu.cn", "Hunan"),
    ("Changsha University of Science and Technology", "长沙理工大学", "csust.edu.cn", "Hunan"),
    ("University of South China", "南华大学", "usc.edu.cn", "Hunan"),
    ("Hunan University of Science and Technology", "湖南科技大学", "hnust.edu.cn", "Hunan"),
    ("University of Science and Technology of China", "中国科学技术大学", "ustc.edu.cn", "Anhui"),
    ("Hefei University of Technology", "合肥工业大学", "hfut.edu.cn", "Anhui"),
    ("Anhui University", "安徽大学", "ahu.edu.cn", "Anhui"),
    ("Anhui Normal University", "安徽师范大学", "ahnu.edu.cn", "Anhui"),
    ("Anhui University of Technology", "安徽工业大学", "ahut.edu.cn", "Anhui"),
    ("Anhui University of Science and Technology", "安徽理工大学", "aust.edu.cn", "Anhui"),
    ("Nankai University", "南开大学", "nankai.edu.cn", "Tianjin"),
    ("Tianjin University", "天津大学", "tju.edu.cn", "Tianjin"),
    ("Hebei University of Technology", "河北工业大学", "hebut.edu.cn", "Tianjin"),
    ("Tiangong University", "天津工业大学", "tiangong.edu.cn", "Tianjin"),
    ("Tianjin University of Technology", "天津理工大学", "tjut.edu.cn", "Tianjin"),
    ("Tianjin Normal University", "天津师范大学", "tjnu.edu.cn", "Tianjin"),
    ("Chongqing University", "重庆大学", "cqu.edu.cn", "Chongqing"),
    ("Southwest University", "西南大学", "swu.edu.cn", "Chongqing"),
    ("Chongqing University of Posts and Telecommunications", "重庆邮电大学", "cqupt.edu.cn", "Chongqing"),
    ("Chongqing Jiaotong University", "重庆交通大学", "cqjtu.edu.cn", "Chongqing"),
    ("Chongqing University of Technology", "重庆理工大学", "cqut.edu.cn", "Chongqing"),
    ("Chongqing Normal University", "重庆师范大学", "cqnu.edu.cn", "Chongqing"),
    ("Xiamen University", "厦门大学", "xmu.edu.cn", "Fujian"),
    ("Fuzhou University", "福州大学", "fzu.edu.cn", "Fujian"),
    ("Fujian Normal University", "福建师范大学", "fjnu.edu.cn", "Fujian"),
    ("Fujian Agriculture and Forestry University", "福建农林大学", "fafu.edu.cn", "Fujian"),
    ("Huaqiao University", "华侨大学", "hqu.edu.cn", "Fujian"),
    ("Dalian University of Technology", "大连理工大学", "dlut.edu.cn", "Liaoning"),
    ("Northeastern University", "东北大学", "neu.edu.cn", "Liaoning"),
    ("Dalian Maritime University", "大连海事大学", "dlmu.edu.cn", "Liaoning"),
    ("Liaoning University", "辽宁大学", "lnu.edu.cn", "Liaoning"),
    ("Shenyang University of Technology", "沈阳工业大学", "sut.edu.cn", "Liaoning"),
    ("Shenyang Aerospace University", "沈阳航空航天大学", "sau.edu.cn", "Liaoning"),
    ("Jilin University", "吉林大学", "jlu.edu.cn", "Jilin"),
    ("Northeast Normal University", "东北师范大学", "nenu.edu.cn", "Jilin"),
    ("Yanbian University", "延边大学", "ybu.edu.cn", "Jilin"),
    ("Changchun University of Science and Technology", "长春理工大学", "cust.edu.cn", "Jilin"),
    ("Zhengzhou University", "郑州大学", "zzu.edu.cn", "Henan"),
    ("Henan University", "河南大学", "henu.edu.cn", "Henan"),
    ("Henan Polytechnic University", "河南理工大学", "hpu.edu.cn", "Henan"),
    ("Henan Normal University", "河南师范大学", "htu.edu.cn", "Henan"),
    ("Henan University of Science and Technology", "河南科技大学", "haust.edu.cn", "Henan"),
    ("Lanzhou University", "兰州大学", "lzu.edu.cn", "Gansu"),
    ("Lanzhou University of Technology", "兰州理工大学", "lut.edu.cn", "Gansu"),
    ("Lanzhou Jiaotong University", "兰州交通大学", "lzjtu.edu.cn", "Gansu"),
    ("Northwest Normal University", "西北师范大学", "nwnu.edu.cn", "Gansu"),
    ("Nanchang University", "南昌大学", "ncu.edu.cn", "Jiangxi"),
    ("Jiangxi Normal University", "江西师范大学", "jxnu.edu.cn", "Jiangxi"),
    ("Jiangxi University of Science and Technology", "江西理工大学", "jxust.edu.cn", "Jiangxi"),
    ("East China Jiaotong University", "华东交通大学", "ecjtu.edu.cn", "Jiangxi"),
    ("Nanchang Hangkong University", "南昌航空大学", "nchu.edu.cn", "Jiangxi"),
    ("Yunnan University", "云南大学", "ynu.edu.cn", "Yunnan"),
    ("Kunming University of Science and Technology", "昆明理工大学", "kust.edu.cn", "Yunnan"),
    ("Yunnan Normal University", "云南师范大学", "ynnu.edu.cn", "Yunnan"),
    ("Guangxi University", "广西大学", "gxu.edu.cn", "Guangxi"),
    ("Guilin University of Electronic Technology", "桂林电子科技大学", "guet.edu.cn", "Guangxi"),
    ("Guilin University of Technology", "桂林理工大学", "glut.edu.cn", "Guangxi"),
    ("Guangxi Normal University", "广西师范大学", "gxnu.edu.cn", "Guangxi"),
    ("Taiyuan University of Technology", "太原理工大学", "tyut.edu.cn", "Shanxi"),
    ("Shanxi University", "山西大学", "sxu.edu.cn", "Shanxi"),
    ("North University of China", "中北大学", "nuc.edu.cn", "Shanxi"),
    ("Xinjiang University", "新疆大学", "xju.edu.cn", "Xinjiang"),
    ("Shihezi University", "石河子大学", "shzu.edu.cn", "Xinjiang"),
]


class DiscoveryEngine:
    """Live Dynamic University Discovery Engine querying Wikidata SPARQL with zero static seed files."""

    def __init__(self):
        self.pending_approval_runs: Dict[str, PreRunCostEstimate] = {}
        self._cached_wikidata_records: List[dict] = []
        self._cache_timestamp: float = 0.0
        self._cache_ttl_seconds: float = 3600.0  # 1 hour cache

    def fetch_all_chinese_universities_live(self) -> List[dict]:
        """Fetches all accredited Chinese universities from Wikidata SPARQL with in-memory TTL caching."""
        now = time.time()
        if self._cached_wikidata_records and (now - self._cache_timestamp) < self._cache_ttl_seconds:
            return self._cached_wikidata_records

        sparql = """
        SELECT DISTINCT ?u ?enName ?zhName ?site ?proj WHERE {
          ?u wdt:P31/wdt:P279* wd:Q3918;
             wdt:P17 wd:Q148;
             wdt:P856 ?site.
          OPTIONAL { ?u rdfs:label ?enName FILTER (lang(?enName) = 'en') }
          OPTIONAL { ?u rdfs:label ?zhName FILTER (lang(?zhName) = 'zh') }
          OPTIONAL {
            ?u (wdt:P463|wdt:P361) ?proj.
            FILTER (?proj IN (wd:Q2502602, wd:Q1970502, wd:Q42308523))
          }
        } LIMIT 1200
        """

        try:
            headers = {"User-Agent": WIKIDATA_USER_AGENT}
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    WIKIDATA_SPARQL_URL,
                    params={"query": sparql, "format": "json"},
                    headers=headers
                )
                if resp.status_code == 200:
                    data = resp.json()
                    bindings = data.get("results", {}).get("bindings", [])
                    self._cached_wikidata_records = bindings
                    self._cache_timestamp = now
                    logger.info(f"Live Wikidata query fetched {len(bindings)} Chinese higher education institutions.")
                    return bindings
                else:
                    logger.error(f"Wikidata returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Failed to fetch live Wikidata universities: {e}")

        return self._cached_wikidata_records

    def filter_universities(
        self,
        regions: Optional[List[str]] = None,
        tiers: Optional[List[str]] = None,
        max_rank: Optional[int] = None,
        keyword: Optional[str] = None,
        source: str = "combined"
    ) -> List[University]:
        """
        Dynamically filters Master's-granting Chinese universities by Source ('combined', 'wikidata', 'moe'),
        Region, Tier/Feasibility, and Keyword, strictly excluding 3-year vocational/junior colleges.
        """
        source_mode = (source or "combined").lower().strip()
        raw_candidates: List[dict] = []
        moe_raw_count = 0
        wikidata_raw_count = 0

        # 1. Ingest Official China MOE / CHSI Master's-Granting Registry when source is 'moe' or 'combined'
        if source_mode in ("moe", "combined"):
            for en_name, zh_name, dom, prov in MOE_MASTERS_REGISTRY:
                moe_raw_count += 1
                raw_candidates.append({
                    "u": {"value": f"moe/{dom}"},
                    "enName": {"value": en_name},
                    "zhName": {"value": zh_name},
                    "site": {"value": f"https://www.{dom}/"},
                    "proj": {"value": ""},
                    "fixed_region": prov,
                    "source_origin": "China MOE Master's Registry (硕士点)",
                    "source_label": "moe_official" if source_mode == "moe" else "combined_triple_check"
                })

        # 2. Ingest Live Wikidata SPARQL Registry when source is 'wikidata' or 'combined'
        if source_mode in ("wikidata", "combined"):
            wd_bindings = self.fetch_all_chinese_universities_live()
            wikidata_raw_count = len(wd_bindings)
            for b in wd_bindings:
                b_copy = dict(b)
                b_copy["source_origin"] = "Wikidata Live SPARQL (Q3918)"
                b_copy["source_label"] = "wikidata_live" if source_mode == "wikidata" else "combined_triple_check"
                raw_candidates.append(b_copy)

        results: List[University] = []
        seen_domains = set()
        seen_names = set()
        excluded_non_edu = 0
        excluded_vocational = 0
        duplicate_merged = 0
        raw_preview_rows: List[dict] = []

        # Build region keywords set if regions are specified
        region_keywords = []
        selected_region_names = set()
        if regions and len(regions) > 0 and "All" not in regions:
            for r in regions:
                r_clean = r.strip()
                selected_region_names.add(r_clean.lower())
                kws = PROVINCE_LOCATION_KEYWORDS.get(r_clean, [r_clean.lower()])
                region_keywords.extend([k.lower() for k in kws])

        kw_clean = keyword.lower().strip() if keyword else None

        for b in raw_candidates:
            raw_site = b.get("site", {}).get("value")
            clean_domain = _clean_domain(raw_site)
            en_name = b.get("enName", {}).get("value") or ""
            zh_name = b.get("zhName", {}).get("value") or ""
            origin_str = b.get("source_origin", "Registry")

            if not clean_domain:
                excluded_non_edu += 1
                continue

            if not clean_domain.endswith(".edu.cn") and not clean_domain.endswith(".ac.cn"):
                excluded_non_edu += 1
                if len(raw_preview_rows) < 250:
                    raw_preview_rows.append({
                        "source_origin": origin_str,
                        "raw_id": b.get("u", {}).get("value", "").split("/")[-1],
                        "raw_en_name": en_name or "-",
                        "raw_zh_name": zh_name or "-",
                        "raw_url": raw_site or "-",
                        "clean_domain": clean_domain,
                        "outcome": "REJECTED (Non-.edu.cn Domain)"
                    })
                continue

            name_key = (en_name.strip().lower() or zh_name.strip().lower())
            if clean_domain in seen_domains or (name_key and name_key in seen_names):
                duplicate_merged += 1
                if len(raw_preview_rows) < 250:
                    raw_preview_rows.append({
                        "source_origin": origin_str,
                        "raw_id": b.get("u", {}).get("value", "").split("/")[-1],
                        "raw_en_name": en_name or "-",
                        "raw_zh_name": zh_name or "-",
                        "raw_url": raw_site or "-",
                        "clean_domain": clean_domain,
                        "outcome": "MERGED (Cross-Source / Subdomain Duplicate)"
                    })
                continue
            if name_key:
                seen_names.add(name_key)

            proj_uri = b.get("proj", {}).get("value", "")
            en_lower = en_name.lower()
            zh_lower = zh_name.lower()
            domain_lower = clean_domain.lower()

            # Exclude non-Master's 3-year vocational / junior / adult colleges
            if any(v in zh_lower for v in VOCATIONAL_EXCLUSION_ZH) or any(v in en_lower for v in VOCATIONAL_EXCLUSION_EN):
                excluded_vocational += 1
                if len(raw_preview_rows) < 250:
                    raw_preview_rows.append({
                        "source_origin": origin_str,
                        "raw_id": b.get("u", {}).get("value", "").split("/")[-1],
                        "raw_en_name": en_name or "-",
                        "raw_zh_name": zh_name or "-",
                        "raw_url": raw_site or "-",
                        "clean_domain": clean_domain,
                        "outcome": "EXCLUDED (3-Year Vocational / Non-Master's)"
                    })
                continue

            # 1. Keyword Filter
            if kw_clean:
                matches_kw = (
                    kw_clean in en_lower or
                    kw_clean in zh_lower or
                    kw_clean in domain_lower
                )
                if not matches_kw:
                    continue

            # Determine region display first
            detected_region = b.get("fixed_region") or "National"
            if detected_region == "National":
                for prov_name, kws in PROVINCE_LOCATION_KEYWORDS.items():
                    if any(k in en_lower or k in zh_lower or k in domain_lower for k in kws):
                        detected_region = prov_name
                        break

            # 2. Regional Filter
            if region_keywords:
                matches_region = (
                    detected_region.lower() in selected_region_names or
                    any(
                        k in en_lower or
                        k in zh_lower or
                        k in domain_lower
                        for k in region_keywords
                    )
                )
                if not matches_region:
                    continue

            # 3. Tier / Competitiveness (Combine Wikidata property + Official MOE 985/211 Domain Registry)
            is_985 = ("Q2502602" in proj_uri) or any(d == clean_domain or clean_domain.endswith("." + d) for d in PROJECT_985_DOMAINS)
            is_211 = ("Q1970502" in proj_uri) or is_985 or any(d == clean_domain or clean_domain.endswith("." + d) for d in PROJECT_211_DOMAINS)
            is_dfc = ("Q42308523" in proj_uri) or is_211

            if is_985:
                tier = FeasibilityTier.TIER_1_DREAM
                notes = "Tier 1 (Dream) — Project 985 / C9 Elite. High competition; top-tier national research labs."
                scholars = [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL, ScholarshipType.PROVINCIAL]
            elif is_211:
                tier = FeasibilityTier.TIER_2_TARGET
                notes = "Tier 2 (Target) — Project 211 / Double First-Class. Strong engineering & AI supervisor quota."
                scholars = [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL, ScholarshipType.PROVINCIAL]
            else:
                tier = FeasibilityTier.TIER_3_SAFETY
                notes = "Tier 3 (Safety) — Accredited Master's-Granting University. High acceptance flexibility."
                scholars = [ScholarshipType.PROVINCIAL, ScholarshipType.PRESIDENTIAL]

            if tiers and len(tiers) > 0 and "All" not in tiers:
                if tier.value not in tiers and tier not in tiers:
                    continue

            # Application fee truth check: never assume 0 RMB unless verified in FEE_WAIVED_DOMAINS
            is_fee_waived = any(d == clean_domain or clean_domain.endswith("." + d) for d in FEE_WAIVED_DOMAINS)
            fee_rmb = 0 if is_fee_waived else None
            fee_note = "0 RMB (Fee Waived)" if is_fee_waived else "400–800 RMB (Standard Est.)"

            official_website = raw_site.strip() if raw_site else f"https://www.{clean_domain}/"

            seen_domains.add(clean_domain)
            if len(raw_preview_rows) < 250:
                raw_preview_rows.append({
                    "source_origin": origin_str,
                    "raw_id": b.get("u", {}).get("value", "").split("/")[-1],
                    "raw_en_name": en_name or "-",
                    "raw_zh_name": zh_name or "-",
                    "raw_url": raw_site or official_website,
                    "clean_domain": clean_domain,
                    "outcome": f"NORMALIZED -> {detected_region} | {tier.value}"
                })

            subj_ranks = SUBJECT_RANKINGS_TABLE.get(clean_domain, {})
            cs_rank = subj_ranks.get("cs")
            if max_rank is not None and (cs_rank is None or cs_rank > max_rank):
                continue

            results.append(University(
                id=clean_domain.replace(".", "-"),
                wikidata_id=b.get("u", {}).get("value", "").split("/")[-1] or None,
                name=en_name or zh_name or clean_domain,
                chinese_name=zh_name or None,
                domain=clean_domain,
                website=official_website,
                region=detected_region,
                tier=tier,
                cs_ranking=cs_rank,
                subject_rankings=subj_ranks,
                is_project_985=is_985,
                is_project_211=is_211,
                is_double_first_class=is_dfc,
                scholarships_available=scholars,
                application_fee_rmb=fee_rmb,
                fee_note=fee_note,
                feasibility_notes=notes,
                pipeline_status="Pending Live Check",
                status_reason="Not live-probed yet. Click 'Verify & Find Dept' or 'Resolve Real Dept Links' to run live check.",
                website_verified=False,
                data_source=b.get("source_label", "combined_triple_check"),
                is_seed=False,
                created_at=datetime.now(timezone.utc)
            ))

        # Sort results by Region (A -> Z), then Tier (Dream -> Target -> Safety)
        results.sort(key=lambda u: (u.region or "ZZZ", u.tier.value if u.tier else "Z", u.name))
        self.last_discovery_audit = {
            "source_mode": source_mode,
            "regions_filter": regions or ["All"],
            "tiers_filter": tiers or ["All"],
            "keyword_filter": keyword or "",
            "moe_raw_count": moe_raw_count,
            "wikidata_raw_count": wikidata_raw_count,
            "total_raw_count": moe_raw_count + wikidata_raw_count,
            "excluded_non_edu_count": excluded_non_edu,
            "excluded_vocational_count": excluded_vocational,
            "duplicate_merged_count": duplicate_merged,
            "normalized_count": len(results),
            "raw_preview_rows": raw_preview_rows,
            "executed_at": datetime.now(timezone.utc).isoformat()
        }
        logger.info(f"Filtered {len(results)} Master's-granting universities (Source: '{source_mode}', Regions: {regions}, Keyword: '{keyword}').")
        return results

    def assess_university(self, domain: str, name: Optional[str] = None) -> University:
        """Determines institutional feasibility tier dynamically without static lookup files."""
        domain_clean = _clean_domain(domain) or domain.lower().strip().replace("http://", "").replace("https://", "").split("/")[0]

        if any(d in domain_clean for d in PROJECT_985_DOMAINS):
            tier = FeasibilityTier.TIER_1_DREAM
            is_985 = True
            is_211 = True
            notes = "Top Tier 1 (Dream) institution (Project 985 / C9). High competition; top-tier research labs."
            scholars = [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL, ScholarshipType.PROVINCIAL]
        elif any(d in domain_clean for d in PROJECT_211_DOMAINS):
            tier = FeasibilityTier.TIER_2_TARGET
            is_985 = False
            is_211 = True
            notes = "Key National Engineering institution (Project 211, Target tier). Strong match."
            scholars = [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL, ScholarshipType.PROVINCIAL]
        else:
            tier = FeasibilityTier.TIER_3_SAFETY
            is_985 = False
            is_211 = False
            notes = "Accredited institution evaluated as Tier 3 (Safety). High flexibility."
            scholars = [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL]

        region = "National"
        for prov, kws in PROVINCE_LOCATION_KEYWORDS.items():
            if any(k in domain_clean for k in kws):
                region = prov
                break

        is_fee_waived = any(d in domain_clean for d in FEE_WAIVED_DOMAINS)
        fee_rmb = 0 if is_fee_waived else None
        fee_note = "0 RMB (Fee Waived)" if is_fee_waived else "400–800 RMB (Standard Est.)"

        subj_ranks = SUBJECT_RANKINGS_TABLE.get(domain_clean, {})
        return University(
            id=domain_clean.replace(".", "-"),
            name=name or domain_clean.split(".")[0].upper() + " University",
            domain=domain_clean,
            website=f"https://www.{domain_clean}/",
            region=region,
            tier=tier,
            cs_ranking=subj_ranks.get("cs"),
            subject_rankings=subj_ranks,
            is_project_985=is_985,
            is_project_211=is_211,
            scholarships_available=scholars,
            application_fee_rmb=fee_rmb,
            fee_note=fee_note,
            feasibility_notes=notes,
            pipeline_status="Pending Live Check",
            website_verified=False,
            data_source="wikidata_live",
            is_seed=False,
            created_at=datetime.now(timezone.utc)
        )

    def enrich_university_record(self, u: University) -> University:
        """Upgrades any cached/stored University record with accurate 985/211 tiers, fees, and authentic status."""
        dom = (u.domain or "").lower().strip()
        is_985 = u.is_project_985 or any(d == dom or dom.endswith("." + d) for d in PROJECT_985_DOMAINS)
        is_211 = u.is_project_211 or is_985 or any(d == dom or dom.endswith("." + d) for d in PROJECT_211_DOMAINS)

        u.is_project_985 = is_985
        u.is_project_211 = is_211
        subj_ranks = SUBJECT_RANKINGS_TABLE.get(dom, {})
        if subj_ranks:
            u.subject_rankings = subj_ranks
            u.cs_ranking = subj_ranks.get("cs")

        if is_985:
            u.tier = FeasibilityTier.TIER_1_DREAM
            if not u.feasibility_notes or "queried from Wikidata" in u.feasibility_notes:
                u.feasibility_notes = "Tier 1 (Dream) — Project 985 / C9 Elite. High competition; top-tier research labs."
            u.scholarships_available = [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL, ScholarshipType.PROVINCIAL]
        elif is_211:
            u.tier = FeasibilityTier.TIER_2_TARGET
            if not u.feasibility_notes or "queried from Wikidata" in u.feasibility_notes:
                u.feasibility_notes = "Tier 2 (Target) — Project 211 / Double First-Class. Strong engineering & AI supervisor quota."
            u.scholarships_available = [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL, ScholarshipType.PROVINCIAL]
        else:
            u.tier = FeasibilityTier.TIER_3_SAFETY
            if not u.feasibility_notes or "queried from Wikidata" in u.feasibility_notes:
                u.feasibility_notes = "Tier 3 (Safety) — Accredited Master's-Granting University. High acceptance flexibility."
            u.scholarships_available = [ScholarshipType.PROVINCIAL, ScholarshipType.PRESIDENTIAL]

        is_fee_waived = any(d == dom or dom.endswith("." + d) for d in FEE_WAIVED_DOMAINS)
        if is_fee_waived:
            u.application_fee_rmb = 0
            u.fee_note = "0 RMB (Fee Waived)"
        else:
            u.application_fee_rmb = None
            u.fee_note = "400–800 RMB (Standard Est.)"

        if not u.website:
            u.website = f"https://www.{dom}/"

        # If record was never live-probed, ensure status is Pending Live Check rather than premature Homepage Verified
        if u.pipeline_status in ("University Homepage Verified", "Homepage Verified") and not u.verified_at:
            u.pipeline_status = "Pending Live Check"
            u.website_verified = False

        # Strip legacy fake cs./ai. template endpoints if present
        if u.department_endpoints:
            cleaned_eps = [
                ep for ep in u.department_endpoints
                if not ep.url.startswith(f"http://cs.{dom}/faculty") and not ep.url.startswith(f"http://ai.{dom}/supervisors")
            ]
            if cleaned_eps and u.pipeline_status == "Pending Live Check":
                for ep in cleaned_eps:
                    if ep.name in ("Verified Institutional Homepage", "Institutional Homepage (Pending Live Check)", "Institutional Homepage"):
                        ep.name = "Institutional Homepage"
                        ep.is_verified = False
                        ep.status = "Pending Live Check"
            u.department_endpoints = cleaned_eps if cleaned_eps else self.discover_department_endpoints(u)
        else:
            u.department_endpoints = self.discover_department_endpoints(u)

        return u

    def discover_department_endpoints(
        self,
        university: University,
        discipline: str = "Computer Science"
    ) -> List[DepartmentEndpoint]:
        """
        Attaches the candidate university homepage marked as Pending Live Check.
        Status only upgrades to Homepage Verified / Department URL Found after live HTTP/Playwright verification.
        """
        homepage = university.website or f"https://www.{university.domain}/"
        if not homepage.startswith("http"):
            homepage = f"https://www.{university.domain}/"

        is_live_verified = bool(university.website_verified and university.verified_at)
        return [
            DepartmentEndpoint(
                name="Verified Institutional Homepage" if is_live_verified else "Institutional Homepage",
                url=homepage,
                is_verified=is_live_verified,
                status="Homepage Verified" if is_live_verified else "Pending Live Check"
            )
        ]

    # ------------------------------------------------------------------ Phase 1 Production 4-Layer Discovery & TTL Cache
    _dept_cache_memory: Dict[tuple[str, str], UniversityDepartmentCache] = {}

    async def get_cached_department(
        self, domain: str, discipline: str
    ) -> Optional[UniversityDepartmentCache]:
        """Checks entity-level cache `(domain, discipline_key)` and validates TTL freshness."""
        from src.core.database import db_manager

        clean_dom = (_clean_domain(domain) or domain).lower().strip()
        disc_key = normalize_discipline_key(discipline)
        now = datetime.now(timezone.utc)

        if db_manager.is_connected and db_manager.db is not None:
            doc = await db_manager.get_collection("university_departments").find_one(
                {"domain": clean_dom, "discipline_key": disc_key}
            )
            if doc:
                doc.pop("_id", None)
                record = UniversityDepartmentCache(**doc)
                exp = record.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp > now and record.status in (
                    TerminalStatus.COMPLETE.value,
                    TerminalStatus.PARTIAL.value,
                ):
                    self._dept_cache_memory[(clean_dom, disc_key)] = record
                    return record

        mem = self._dept_cache_memory.get((clean_dom, disc_key))
        if mem:
            exp = mem.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now and mem.status in (
                TerminalStatus.COMPLETE.value,
                TerminalStatus.PARTIAL.value,
            ):
                return mem
        return None

    async def save_department_cache(self, record: UniversityDepartmentCache) -> None:
        """Persists entity-level department & faculty roster cache to memory and MongoDB (`university_departments`)."""
        from src.core.database import db_manager

        clean_dom = (_clean_domain(record.domain) or record.domain).lower().strip()
        record.domain = clean_dom
        self._dept_cache_memory[(clean_dom, record.discipline_key)] = record

        if db_manager.is_connected and db_manager.db is not None:
            payload = json.loads(record.model_dump_json())
            await db_manager.get_collection("university_departments").update_one(
                {"domain": clean_dom, "discipline_key": record.discipline_key},
                {"$set": payload},
                upsert=True,
            )

    @staticmethod
    def _classify_http_exception(exc: Exception) -> ErrorCode:
        msg = str(exc).lower()
        if isinstance(exc, httpx.TimeoutException) or "timed out" in msg or "timeout" in msg:
            return ErrorCode.CONNECTION_TIMEOUT
        if any(k in msg for k in ("getaddrinfo", "name or service not known", "nodename nor servname", "nxdomain", "dns")):
            return ErrorCode.DNS_RESOLUTION_FAILED
        if any(k in msg for k in ("ssl", "certificate", "tls", "handshake")):
            return ErrorCode.SSL_ERROR
        return ErrorCode.HTTP_5XX_SERVER_ERROR

    async def _typed_fetch_url(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        domain: str,
        uni_name: str,
        trace_id: str,
        discipline_key: str,
        layer: str = "L1_HTTP_PROBE",
        allow_playwright: bool = True,
        apply_rate_limit: bool = True,
    ) -> StepResult[tuple[str, str]]:
        """
        Typed HTTP fetch with transient retry/backoff, meta-refresh support, explicit ErrorCode classification,
        and controlled Layer 4 Playwright fallback strictly on WAF (403/412/429/521) or anti-bot JS splash.
        """
        import asyncio
        import re
        from urllib.parse import urljoin
        from src.services.scraper import decode_html, harvester

        if apply_rate_limit:
            await concurrency_controller.wait_for_domain(domain)

        last_err_code = ErrorCode.CONNECTION_TIMEOUT
        last_err_detail = ""
        last_status: Optional[int] = None
        waf_detected = False
        t0 = time.monotonic()

        # Max 2 attempts for transient errors (TIMEOUT, 502, 503, 504)
        for attempt in (1, 2):
            try:
                async with concurrency_controller.http_semaphore:
                    resp = await client.get(url, headers=headers)
                last_status = resp.status_code
                latency = int((time.monotonic() - t0) * 1000)

                if resp.status_code == 200:
                    text = decode_html(resp.content, resp.headers.get("content-type", ""))
                    if len(text) > 250 and "<a" in text.lower():
                        return StepResult(
                            ok=True,
                            value=(text, str(resp.url)),
                            error_code=ErrorCode.NONE,
                            layer=layer,
                            http_status=200,
                            latency_ms=latency,
                            attempt=attempt,
                        )

                    # Client-side meta-refresh or location.href redirect
                    meta_match = re.search(r'url\s*=\s*[\'"]?([^\'">\s]+)', text, re.IGNORECASE)
                    if not meta_match:
                        meta_match = re.search(r'location\.href\s*=\s*[\'"]([^\'"]+)[\'"]', text, re.IGNORECASE)
                    if meta_match:
                        redirect_target = meta_match.group(1).strip()
                        if redirect_target and not redirect_target.startswith("javascript:"):
                            next_url = urljoin(str(resp.url), redirect_target)
                            async with concurrency_controller.http_semaphore:
                                resp2 = await client.get(next_url, headers=headers)
                            if resp2.status_code == 200:
                                text2 = decode_html(resp2.content, resp2.headers.get("content-type", ""))
                                if len(text2) > 250 and "<a" in text2.lower():
                                    return StepResult(
                                        ok=True,
                                        value=(text2, str(resp2.url)),
                                        error_code=ErrorCode.NONE,
                                        layer=layer,
                                        http_status=200,
                                        latency_ms=int((time.monotonic() - t0) * 1000),
                                        attempt=attempt,
                                    )

                    text_low = text.lower()
                    if any(
                        w in text_low
                        for w in ("waf", "challenge", "captcha", "security check", "安全验证", "防火墙", "antispider", "browser check")
                    ):
                        waf_detected = True
                        last_err_code = ErrorCode.WAF_CHALLENGE_BLOCKED
                        last_err_detail = f"Client-side WAF/JS splash detected on {url}"
                        break

                    # Sparse JS shell without static anchors
                    waf_detected = True
                    last_err_code = ErrorCode.WAF_CHALLENGE_BLOCKED
                    last_err_detail = f"Sparse HTML shell ({len(text)} chars, 0 static links) on {url}"
                    break

                if resp.status_code in (403, 412, 429, 521):
                    waf_detected = True
                    last_err_code = ErrorCode.WAF_CHALLENGE_BLOCKED
                    last_err_detail = f"HTTP {resp.status_code} WAF challenge on {url}"
                    break

                if resp.status_code in (502, 503, 504) and attempt == 1:
                    await asyncio.sleep(1.0)
                    continue

                if 400 <= resp.status_code < 500:
                    last_err_code = ErrorCode.HTTP_4XX_NOT_FOUND
                    last_err_detail = f"HTTP {resp.status_code} on {url}"
                    break

                last_err_code = ErrorCode.HTTP_5XX_SERVER_ERROR
                last_err_detail = f"HTTP {resp.status_code} on {url}"
                break

            except Exception as exc:
                last_err_code = self._classify_http_exception(exc)
                last_err_detail = f"{type(exc).__name__}: {exc}"
                if last_err_code == ErrorCode.CONNECTION_TIMEOUT and attempt == 1:
                    await asyncio.sleep(1.0)
                    continue
                break

        # Layer 4 Controlled Playwright Fallback (strictly on WAF / JS shell)
        if waf_detected and allow_playwright:
            pw_allowed, pw_err = policy_manager.check_playwright_allowed()
            if not pw_allowed:
                phase1_logger.emit(
                    trace_id=trace_id,
                    university_domain=domain,
                    discipline=discipline_key,
                    layer="L4_PLAYWRIGHT",
                    action="FALLBACK_SKIPPED",
                    level="WARNING",
                    http_status=last_status,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error_code=pw_err,
                    error_detail="Playwright fallback disabled by admin policy",
                )
            else:
                phase1_logger.emit(
                    trace_id=trace_id,
                    university_domain=domain,
                    discipline=discipline_key,
                    layer=layer,
                    action="FALLBACK_TRIGGERED",
                    next_layer="L4_PLAYWRIGHT",
                    level="WARNING",
                    http_status=last_status,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error_code=last_err_code,
                    error_detail=last_err_detail,
                )
                pw_t0 = time.monotonic()
                try:
                    async with concurrency_controller.playwright_semaphore:
                        await policy_manager.record_playwright_page()
                        html, final_url = await harvester.fetch_html_dynamic(url)
                    if html and len(html) > 250:
                        return StepResult(
                            ok=True,
                            value=(html, final_url),
                            error_code=ErrorCode.NONE,
                            layer="L4_PLAYWRIGHT",
                            http_status=200,
                            latency_ms=int((time.monotonic() - pw_t0) * 1000),
                        )
                except Exception as pw_exc:
                    last_err_code = ErrorCode.WAF_CHALLENGE_BLOCKED
                    last_err_detail = f"Playwright fallback failed: {pw_exc}"

        return StepResult(
            ok=False,
            value=None,
            error_code=last_err_code,
            error_detail=last_err_detail,
            layer=layer,
            http_status=last_status,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    @staticmethod
    def verify_content_gate(html: str, url: str, require_faculty_markers: bool = False) -> StepResult[bool]:
        """
        HTTP 200 Content Gate:
        - Rejects login/SSO/VPN/news pages with FALSE_POSITIVE_PAGE.
        - When `require_faculty_markers=True`, confirms keyword density for faculty/supervisors (`导师/师资/教授/faculty`).
        """
        from bs4 import BeautifulSoup

        u_low = (url or "").lower()
        auth_url_exclusions = ("login", "authserver", "webvpn", "clientvpn", "cas.", "sso.", "passport", "userlogin")
        if any(ak in u_low for ak in auth_url_exclusions):
            return StepResult(
                ok=False,
                value=False,
                error_code=ErrorCode.FALSE_POSITIVE_PAGE,
                error_detail=f"URL matches SSO/Auth exclusion: {url}",
                layer="VERIFY_CONTENT_GATE",
            )

        soup = BeautifulSoup(html or "", "html.parser")
        title_text = (soup.title.get_text(" ", strip=True) if soup.title else "").lower()
        auth_title_exclusions = ("统一身份认证", "用户登录", "系统登录", "认证中心", "vpn登录", "单点登录")
        if any(at in title_text for at in auth_title_exclusions):
            return StepResult(
                ok=False,
                value=False,
                error_code=ErrorCode.FALSE_POSITIVE_PAGE,
                error_detail=f"Page title indicates SSO/Login portal: {title_text}",
                layer="VERIFY_CONTENT_GATE",
            )

        body_text = soup.get_text(" ", strip=True).lower()
        if len(body_text) < 80:
            return StepResult(
                ok=False,
                value=False,
                error_code=ErrorCode.FALSE_POSITIVE_PAGE,
                error_detail="Page body text too short (< 80 chars)",
                layer="VERIFY_CONTENT_GATE",
            )

        if require_faculty_markers:
            roster_tokens = (
                "导师", "硕士生导师", "博士生导师", "硕导", "博导", "师资", "教授",
                "副教授", "研究方向", "教师", "faculty", "professor", "supervisor"
            )
            hits = sum(1 for tok in roster_tokens if tok in body_text)
            if hits < 2:
                return StepResult(
                    ok=False,
                    value=False,
                    error_code=ErrorCode.FACULTY_ROSTER_NOT_FOUND,
                    error_detail=f"Insufficient faculty keyword density ({hits} hits) on {url}",
                    layer="VERIFY_CONTENT_GATE",
                )

        return StepResult(ok=True, value=True, error_code=ErrorCode.NONE, layer="VERIFY_CONTENT_GATE")

    async def discover_department_4layer(
        self,
        university: University,
        discipline: str = "Computer Science",
        trace_id: str = "manual",
        force_refresh: bool = False,
        scorecard: Optional[JobScorecard] = None,
    ) -> UniversityDepartmentCache:
        """
        Production 4-Layer Deterministic Discovery Pipeline:
        - Cache Check: Entity cache `(domain, discipline_key)` with TTL (90 days COMPLETE, 7 days NEEDS_REVIEW).
        - Layer 1 (L1_HTTP_PROBE): Fast httpx homepage probe (+ L4 Playwright only on WAF 403/412/521).
        - Layer 2 (L2_NAV_PARSE): On-site navigation parse (Homepage + `<nav>`/`<select>` + '院系设置' + Faculty Roster links).
        - Layer 3 (L3_SEARCH_API): Targeted `site:<domain>` search via SearchFirstProvider (replaces 18-subdomain brute-force).
        - Layer 4 (L4_PLAYWRIGHT): Controlled 1-at-a-time headless Chromium fallback strictly on WAF/JS challenge.
        """
        from datetime import timedelta
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        t_start = time.monotonic()
        clean_dom = (_clean_domain(university.domain) or university.domain).lower().strip()
        disc_key = normalize_discipline_key(discipline)

        # 0. Entity Cache Check
        if not force_refresh:
            cached = await self.get_cached_department(clean_dom, discipline)
            if cached is not None:
                latency_ms = int((time.monotonic() - t_start) * 1000)
                phase1_logger.emit(
                    trace_id=trace_id,
                    university_domain=clean_dom,
                    discipline=disc_key,
                    layer="CACHE",
                    action="CACHE_HIT",
                    latency_ms=latency_ms,
                )
                if scorecard is not None:
                    scorecard.record_outcome(
                        status=TerminalStatus(cached.status),
                        resolved_by_layer="CACHE",
                        latency_ms=latency_ms,
                        homepage_ok=bool(cached.homepage_url),
                        dept_ok=bool(cached.department_url),
                        roster_ok=bool(cached.faculty_roster_urls),
                        from_cache=True,
                    )
                return cached

        discovery_path: List[str] = ["CACHE_MISS"]
        resolved_by_layer: Optional[str] = None
        last_error_code = ErrorCode.NONE
        last_error_detail = ""
        search_calls_made = 0
        total_cost_usd = 0.0

        def _safe_urljoin(base_u: str, raw_href: str) -> Optional[str]:
            try:
                cleaned_h = (raw_href or "").strip()
                if not cleaned_h or cleaned_h.startswith(("javascript:", "#", "mailto:", "tel:", "data:")):
                    return None
                joined = urljoin(base_u, cleaned_h)
                if any(joined.lower().endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".jpg", ".png")):
                    return None
                return joined
            except Exception:
                return None

        candidates_root: List[str] = []
        if university.website:
            candidates_root.append(university.website)
        for cand in (
            f"https://www.{clean_dom}/",
            f"http://www.{clean_dom}/",
            f"https://{clean_dom}/",
            f"http://{clean_dom}/",
        ):
            if cand not in candidates_root:
                candidates_root.append(cand)

        homepage_html: Optional[str] = None
        working_root: Optional[str] = None
        playwright_attempted = False

        headers = {
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        timeout_cfg = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout_cfg, follow_redirects=True, verify=False) as client:
            # ---------------- LAYER 1: Homepage Probe (with L4 Playwright WAF fallback once) ----------------
            for idx, root_url in enumerate(candidates_root):
                res = await self._typed_fetch_url(
                    client=client,
                    url=root_url,
                    headers=headers,
                    domain=clean_dom,
                    uni_name=university.name,
                    trace_id=trace_id,
                    discipline_key=disc_key,
                    layer="L1_HTTP_PROBE",
                    allow_playwright=(not playwright_attempted),
                    apply_rate_limit=(idx > 0),
                )
                if res.layer == "L4_PLAYWRIGHT":
                    playwright_attempted = True
                if res.ok and res.value:
                    homepage_html, working_root = res.value
                    discovery_path.append("L4_PLAYWRIGHT_OK" if res.layer == "L4_PLAYWRIGHT" else "L1_HTTP_OK")
                    if res.layer == "L4_PLAYWRIGHT":
                        resolved_by_layer = "L4_PLAYWRIGHT"
                    phase1_logger.emit(
                        trace_id=trace_id,
                        university_domain=clean_dom,
                        discipline=disc_key,
                        layer=res.layer,
                        action="HOMEPAGE_VERIFIED",
                        http_status=res.http_status,
                        latency_ms=res.latency_ms,
                    )
                    break
                else:
                    last_error_code = res.error_code
                    last_error_detail = res.error_detail
                    if res.error_code == ErrorCode.WAF_CHALLENGE_BLOCKED:
                        playwright_attempted = True

            if not homepage_html:
                discovery_path.append(f"L1_FAIL:{last_error_code.value}")
                phase1_logger.emit(
                    trace_id=trace_id,
                    university_domain=clean_dom,
                    discipline=disc_key,
                    layer="L1_HTTP_PROBE",
                    action="FALLBACK_TRIGGERED",
                    next_layer="L3_SEARCH_API",
                    level="WARNING",
                    error_code=last_error_code,
                    error_detail=last_error_detail,
                )

            # ---------------- LAYER 2: On-Site Navigation & '院系设置' Parsing ----------------
            zh_terms, en_terms = DISCIPLINE_SYNONYMS.get(disc_key, DISCIPLINE_SYNONYMS["computer_science"])
            dept_keywords = [t.lower() for t in (zh_terms + en_terms)] + [
                "计算机", "人工智能", "软件", "信息工程", "信息科学", "智能科学", "网络空间", "大数据",
                "computer", "artificial intelligence", "software", "informatics", "computing"
            ]
            unit_suffixes = ("学院", "系", "学部", "研究院", "school", "college", "department", "faculty")
            nav_keywords = (
                "院系设置", "机构设置", "教学单位", "学院设置", "二级学院", "学部院系",
                "院系总览", "学院导航", "教学机构", "院系所", "教学科研单位", "组织机构"
            )
            news_exclude_keywords = (
                "活动", "通知", "公告", "新闻", "讲座", "招聘", "公示", "大赛", "会议", "党支部", "获批", "举行", "喜报"
            )
            auth_url_exclusions = ("login", "authserver", "webvpn", "clientvpn", "cas", "sso", "passport", "userlogin")

            def _is_valid_dept_link(text_str: str, url_str: str) -> bool:
                t_clean = (text_str or "").strip()
                t_low = t_clean.lower()
                u_low = (url_str or "").lower()
                if not t_clean or len(t_clean) > 36:
                    return False
                if any(nk in u_low for nk in ("/info/", "/news/", "/content/", "/article/", "/notice/")):
                    return False
                if any(ak in u_low for ak in auth_url_exclusions):
                    return False
                if any(nk in t_low for nk in news_exclude_keywords):
                    return False
                return any(k in t_low for k in dept_keywords) and any(u in t_low for u in unit_suffixes)

            def _extract_links_including_dropdowns(html_doc: str, base_u: str) -> List[tuple[str, str]]:
                soup_doc = BeautifulSoup(html_doc, "html.parser")
                pairs: List[tuple[str, str]] = []
                for a in soup_doc.find_all("a", href=True):
                    txt = a.get_text(" ", strip=True) or a.get("title", "")
                    f_u = _safe_urljoin(base_u, a.get("href", ""))
                    if txt and f_u:
                        pairs.append((txt.strip(), f_u))
                # Also inspect <select><option value="http..."> college dropdowns common on .edu.cn
                for opt in soup_doc.find_all("option", value=True):
                    val = (opt.get("value") or "").strip()
                    txt = opt.get_text(" ", strip=True)
                    if val.startswith(("http://", "https://", "/")):
                        f_u = _safe_urljoin(base_u, val)
                        if txt and f_u:
                            pairs.append((txt.strip(), f_u))
                return pairs

            discovered_depts: List[tuple[str, str]] = []
            faculty_rosters: List[FacultyRosterEndpoint] = []

            if homepage_html and working_root:
                nav_links: List[tuple[str, str]] = []
                all_home_links = _extract_links_including_dropdowns(homepage_html, working_root)
                for text, full_url in all_home_links:
                    if any(nk in text for nk in nav_keywords) and len(text) <= 16:
                        nav_links.append((text, full_url))
                    elif _is_valid_dept_link(text, full_url):
                        discovered_depts.append((text, full_url))

                if nav_links and not discovered_depts:
                    nav_links.sort(key=lambda x: 0 if ("院系" in x[0] or "学院" in x[0]) else 1)
                    for nav_text, nav_url in nav_links[:2]:
                        nav_res = await self._typed_fetch_url(
                            client=client,
                            url=nav_url,
                            headers=headers,
                            domain=clean_dom,
                            uni_name=university.name,
                            trace_id=trace_id,
                            discipline_key=disc_key,
                            layer="L2_NAV_PARSE",
                            allow_playwright=False,
                        )
                        if nav_res.ok and nav_res.value:
                            nav_html, nav_final = nav_res.value
                            for t, f_url in _extract_links_including_dropdowns(nav_html, nav_final):
                                if _is_valid_dept_link(t, f_url):
                                    discovered_depts.append((t, f_url))
                        if discovered_depts:
                            break

                if discovered_depts:
                    discovery_path.append("L2_NAV_DEPT_HIT")
                    if not resolved_by_layer:
                        resolved_by_layer = "L2_HTTP_NAV"
                else:
                    discovery_path.append("L2_NAV_FAIL")
                    last_error_code = ErrorCode.DEPT_LINK_NOT_FOUND
                    last_error_detail = f"Homepage parsed ({len(all_home_links)} links), 0 matched {disc_key} department"
                    phase1_logger.emit(
                        trace_id=trace_id,
                        university_domain=clean_dom,
                        discipline=disc_key,
                        layer="L2_NAV_PARSE",
                        action="FALLBACK_TRIGGERED",
                        next_layer="L3_SEARCH_API",
                        level="WARNING",
                        http_status=200,
                        error_code=last_error_code,
                        error_detail=last_error_detail,
                    )

            # Deduplicate discovered departments and scan for Faculty Roster links
            unique_depts: List[tuple[str, str]] = []
            seen_dept_urls = set()
            for d_name, d_url in discovered_depts:
                if d_url not in seen_dept_urls:
                    seen_dept_urls.add(d_url)
                    unique_depts.append((d_name, d_url))

            for d_name, d_url in unique_depts[:3]:
                d_res = await self._typed_fetch_url(
                    client=client,
                    url=d_url,
                    headers=headers,
                    domain=clean_dom,
                    uni_name=university.name,
                    trace_id=trace_id,
                    discipline_key=disc_key,
                    layer="L2_NAV_PARSE",
                    allow_playwright=False,
                )
                if d_res.ok and d_res.value:
                    d_html, d_final = d_res.value
                    gate = self.verify_content_gate(d_html, d_final, require_faculty_markers=False)
                    if not gate.ok:
                        continue
                    for ft, fac_url in _extract_links_including_dropdowns(d_html, d_final):
                        if len(ft) > 25:
                            continue
                        ft_low = ft.lower()
                        for marker, deg in FACULTY_ROSTER_MARKERS:
                            if marker in ft_low:
                                faculty_rosters.append(
                                    FacultyRosterEndpoint(
                                        url=fac_url,
                                        label_zh=f"{d_name} > {ft}",
                                        inherited_degree=deg,
                                    )
                                )
                                break
                if faculty_rosters:
                    discovery_path.append("L2_ROSTER_HIT")
                    break

            # ---------------- LAYER 3: Search-First Fallback (Replaces 18 Hardcoded Subdomains) ----------------
            if not unique_depts or not faculty_rosters:
                search_res = await search_provider.search_department_and_roster(clean_dom, discipline)
                if search_res.cost_usd > 0 or search_res.ok:
                    search_calls_made += 1
                    total_cost_usd += search_res.cost_usd

                if search_res.ok and search_res.value:
                    discovery_path.append("L3_SEARCH_HIT")
                    phase1_logger.emit(
                        trace_id=trace_id,
                        university_domain=clean_dom,
                        discipline=disc_key,
                        layer="L3_SEARCH_API",
                        action="CANDIDATES_FOUND",
                        http_status=search_res.http_status,
                        latency_ms=search_res.latency_ms,
                        cost_usd=search_res.cost_usd,
                    )
                    for cand in search_res.value[:3]:
                        cand_fetch = await self._typed_fetch_url(
                            client=client,
                            url=cand.url,
                            headers=headers,
                            domain=clean_dom,
                            uni_name=university.name,
                            trace_id=trace_id,
                            discipline_key=disc_key,
                            layer="L3_SEARCH_VERIFY",
                            allow_playwright=(not playwright_attempted),
                        )
                        if not cand_fetch.ok or not cand_fetch.value:
                            last_error_code = cand_fetch.error_code
                            last_error_detail = cand_fetch.error_detail
                            continue

                        c_html, c_final = cand_fetch.value
                        c_gate = self.verify_content_gate(
                            c_html, c_final, require_faculty_markers=cand.is_faculty_roster
                        )
                        if not c_gate.ok:
                            last_error_code = c_gate.error_code
                            last_error_detail = c_gate.error_detail
                            continue

                        if not working_root:
                            working_root = f"https://www.{clean_dom}/"
                        if not unique_depts:
                            unique_depts.append((cand.title or discipline, c_final))
                        if cand.is_faculty_roster:
                            faculty_rosters.append(
                                FacultyRosterEndpoint(
                                    url=c_final,
                                    label_zh=cand.inherited_label_zh or cand.title or "师资队伍",
                                    inherited_degree=cand.inherited_degree or "master",
                                )
                            )
                            discovery_path.append("VERIFY_OK")
                            resolved_by_layer = "L3_SEARCH_API"
                            break
                        else:
                            # Inspect candidate department page for faculty roster link
                            for ft, fac_url in _extract_links_including_dropdowns(c_html, c_final):
                                if len(ft) > 25:
                                    continue
                                for marker, deg in FACULTY_ROSTER_MARKERS:
                                    if marker in ft.lower():
                                        faculty_rosters.append(
                                            FacultyRosterEndpoint(
                                                url=fac_url,
                                                label_zh=f"{cand.title} > {ft}",
                                                inherited_degree=deg,
                                            )
                                        )
                                        break
                            if faculty_rosters:
                                discovery_path.append("VERIFY_OK")
                                resolved_by_layer = "L3_SEARCH_API"
                                break
                else:
                    discovery_path.append(f"L3_SEARCH_FAIL:{search_res.error_code.value}")
                    if last_error_code == ErrorCode.NONE:
                        last_error_code = search_res.error_code
                        last_error_detail = search_res.error_detail
                    phase1_logger.emit(
                        trace_id=trace_id,
                        university_domain=clean_dom,
                        discipline=disc_key,
                        layer="L3_SEARCH_API",
                        action="SEARCH_FALLBACK_FAILED",
                        level="WARNING",
                        http_status=search_res.http_status,
                        latency_ms=search_res.latency_ms,
                        error_code=search_res.error_code,
                        error_detail=search_res.error_detail,
                        cost_usd=search_res.cost_usd,
                    )

        # ---------------- Determine Honest Terminal Status & TTL ----------------
        now_utc = datetime.now(timezone.utc)
        dept_name_zh = unique_depts[0][0] if unique_depts else None
        dept_url = unique_depts[0][1] if unique_depts else None

        if working_root and dept_url and faculty_rosters:
            term_status = TerminalStatus.COMPLETE
            confidence = ConfidenceLevel.HIGH
            last_error_code = ErrorCode.NONE
            last_error_detail = ""
            ttl_days = settings.PHASE1_CACHE_TTL_DAYS
            if not resolved_by_layer:
                resolved_by_layer = "L2_HTTP_NAV"
        elif working_root and dept_url:
            term_status = TerminalStatus.PARTIAL
            confidence = ConfidenceLevel.MEDIUM
            if last_error_code == ErrorCode.NONE:
                last_error_code = ErrorCode.FACULTY_ROSTER_NOT_FOUND
                last_error_detail = f"Department found ({dept_url}), but no faculty roster link verified"
            ttl_days = settings.PHASE1_CACHE_TTL_DAYS
            if not resolved_by_layer:
                resolved_by_layer = "L2_HTTP_NAV"
        elif working_root and last_error_code == ErrorCode.DEPT_LINK_NOT_FOUND:
            term_status = TerminalStatus.NOT_FOUND
            confidence = ConfidenceLevel.MEDIUM
            ttl_days = settings.PHASE1_REVIEW_TTL_DAYS
        else:
            term_status = TerminalStatus.NEEDS_REVIEW
            confidence = ConfidenceLevel.LOW
            if last_error_code == ErrorCode.NONE:
                last_error_code = ErrorCode.DEPT_LINK_NOT_FOUND
            ttl_days = settings.PHASE1_REVIEW_TTL_DAYS

        record = UniversityDepartmentCache(
            domain=clean_dom,
            university_name=university.name,
            discipline_key=disc_key,
            department_name_zh=dept_name_zh,
            department_name_en=discipline,
            department_url=dept_url,
            homepage_url=working_root,
            faculty_roster_urls=faculty_rosters,
            status=term_status.value,
            confidence=confidence.value,
            discovery_path=discovery_path,
            last_error_code=last_error_code.value,
            error_detail=last_error_detail,
            resolved_by_layer=resolved_by_layer,
            fetched_at=now_utc,
            expires_at=now_utc + timedelta(days=ttl_days),
        )
        await self.save_department_cache(record)

        total_latency = int((time.monotonic() - t_start) * 1000)
        phase1_logger.emit(
            trace_id=trace_id,
            university_domain=clean_dom,
            discipline=disc_key,
            layer=resolved_by_layer or "TERMINAL",
            action=f"TERMINAL_{term_status.value}",
            level="INFO" if term_status in (TerminalStatus.COMPLETE, TerminalStatus.PARTIAL) else "WARNING",
            latency_ms=total_latency,
            error_code=last_error_code,
            error_detail=last_error_detail,
            cost_usd=total_cost_usd,
        )

        if scorecard is not None:
            scorecard.record_outcome(
                status=term_status,
                resolved_by_layer=resolved_by_layer,
                latency_ms=total_latency,
                homepage_ok=bool(working_root),
                dept_ok=bool(dept_url),
                roster_ok=bool(faculty_rosters),
                from_cache=False,
                error_code=last_error_code,
                search_calls=search_calls_made,
                cost_usd=total_cost_usd,
            )

        return record

    async def resolve_department_from_homepage(
        self,
        university: University,
        discipline: str = "Computer Science",
        trace_id: str = "resolve-sync",
        force_refresh: bool = False,
        scorecard: Optional[JobScorecard] = None,
    ) -> University:
        """
        Executes the 4-Layer Deterministic Discovery Pipeline and maps results onto the `University` model
        for backward-compatible UI rendering and persistence.
        """
        record = await self.discover_department_4layer(
            university=university,
            discipline=discipline,
            trace_id=trace_id,
            force_refresh=force_refresh,
            scorecard=scorecard,
        )

        endpoints: List[DepartmentEndpoint] = []
        if record.homepage_url:
            university.website = record.homepage_url
            university.website_verified = True
            university.verified_at = record.fetched_at
            endpoints.append(
                DepartmentEndpoint(
                    name="🏛️ Verified Institutional Homepage (Step 1 OK)",
                    url=record.homepage_url,
                    is_verified=True,
                    status="Homepage Verified",
                )
            )

        for roster in record.faculty_roster_urls:
            endpoints.append(
                DepartmentEndpoint(
                    name=f"👨‍🏫 { roster.label_zh }",
                    url=roster.url,
                    is_verified=True,
                    status="Faculty Page Found",
                )
            )

        if record.department_url and not record.faculty_roster_urls:
            endpoints.append(
                DepartmentEndpoint(
                    name=f"🎓 {record.department_name_zh or discipline}",
                    url=record.department_url,
                    is_verified=True,
                    status="Department URL Found",
                )
            )

        if record.status == TerminalStatus.COMPLETE.value:
            university.pipeline_status = "Faculty Page Found"
            university.status_reason = (
                f"COMPLETE ({record.resolved_by_layer}): Faculty Roster Verified at "
                f"{record.faculty_roster_urls[0].url} | Path: {' -> '.join(record.discovery_path)}"
            )
            university.resolved_at = record.fetched_at
        elif record.status == TerminalStatus.PARTIAL.value:
            university.pipeline_status = "Department URL Found"
            university.status_reason = (
                f"PARTIAL ({record.resolved_by_layer}): Dept Found ({record.department_url}), "
                f"Roster Pending [{record.last_error_code}] | Path: {' -> '.join(record.discovery_path)}"
            )
            university.resolved_at = record.fetched_at
        elif record.homepage_url:
            university.pipeline_status = "Homepage OK · Dept Not Found"
            university.status_reason = (
                f"{record.status} [{record.last_error_code}]: {record.error_detail} | "
                f"Path: {' -> '.join(record.discovery_path)}"
            )
        else:
            university.pipeline_status = "Step 1 Failed: Homepage Unreachable"
            university.status_reason = (
                f"NEEDS_REVIEW [{record.last_error_code}]: {record.error_detail} | "
                f"Path: {' -> '.join(record.discovery_path)}"
            )
            endpoints = [
                DepartmentEndpoint(
                    name="Institutional Homepage (Step 1 Unreachable)",
                    url=university.website or f"https://www.{university.domain}/",
                    is_verified=False,
                    status="Step 1 Failed: Homepage Unreachable",
                )
            ]

        university.department_endpoints = endpoints
        return university

    def calculate_cost_estimate(self, department_endpoints: List[DepartmentEndpoint]) -> PreRunCostEstimate:
        """Calculates estimated pages, faculty count, tokens, and runtime."""
        num_endpoints = len(department_endpoints)
        pages_per_dept = 3
        professors_per_dept = 12
        tokens_per_professor = 650
        seconds_per_profile = 2

        est_pages = num_endpoints * pages_per_dept
        est_faculty = num_endpoints * professors_per_dept
        est_tokens = est_faculty * tokens_per_professor
        est_runtime = (num_endpoints * 3) + (est_faculty * seconds_per_profile)

        estimate = PreRunCostEstimate(
            total_target_departments=num_endpoints,
            estimated_pages_to_crawl=est_pages,
            estimated_faculty_count=est_faculty,
            estimated_gemini_tokens=est_tokens,
            estimated_runtime_seconds=est_runtime,
            is_approved=False
        )
        return estimate

    def approve_estimate(self, estimate: PreRunCostEstimate) -> PreRunCostEstimate:
        """Unlocks the confirmation gate."""
        estimate.is_approved = True
        estimate.approved_at = datetime.now(timezone.utc)
        return estimate


discovery_engine = DiscoveryEngine()
