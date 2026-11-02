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
from src.models.university import (
    DepartmentEndpoint,
    FeasibilityTier,
    PreRunCostEstimate,
    ScholarshipType,
    University,
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

            results.append(University(
                id=clean_domain.replace(".", "-"),
                wikidata_id=b.get("u", {}).get("value", "").split("/")[-1] or None,
                name=en_name or zh_name or clean_domain,
                chinese_name=zh_name or None,
                domain=clean_domain,
                website=official_website,
                region=detected_region,
                tier=tier,
                cs_ranking=None,
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

        return University(
            id=domain_clean.replace(".", "-"),
            name=name or domain_clean.split(".")[0].upper() + " University",
            domain=domain_clean,
            website=f"https://www.{domain_clean}/",
            region=region,
            tier=tier,
            cs_ranking=None,
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
                    if ep.name in ("Verified Institutional Homepage", "Institutional Homepage (Pending Live Check)"):
                        ep.name = "Institutional Homepage (Pending Live Check)"
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
                name="Verified Institutional Homepage" if is_live_verified else "Institutional Homepage (Pending Live Check)",
                url=homepage,
                is_verified=is_live_verified,
                status="Homepage Verified" if is_live_verified else "Pending Live Check"
            )
        ]

    async def _fetch_with_waf_fallback(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        uni_name: str,
        allow_playwright: bool = True
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Attempts fast httpx GET first (including client-side meta-refresh / location.href redirects);
        if blocked by anti-bot WAF (HTTP 412 Precondition Failed, 403, 521)
        or explicit JS challenge, falls back to 1-at-a-time headless Playwright Chromium.
        Generic timeouts, connection resets, and dead hosts fail fast and NEVER trigger Playwright.
        """
        import re
        from urllib.parse import urljoin
        from src.services.scraper import harvester, decode_html

        waf_blocked = False
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                text = decode_html(resp.content, resp.headers.get("content-type", ""))
                if len(text) > 250 and "<a" in text.lower():
                    return text, str(resp.url)

                # Edge case: Tiny HTML with <meta http-equiv="refresh" content="0;url=..."> or window.location.href
                meta_match = re.search(r'url\s*=\s*[\'"]?([^\'">\s]+)', text, re.IGNORECASE)
                if not meta_match:
                    meta_match = re.search(r'location\.href\s*=\s*[\'"]([^\'"]+)[\'"]', text, re.IGNORECASE)
                if meta_match:
                    redirect_target = meta_match.group(1).strip()
                    if redirect_target and not redirect_target.startswith("javascript:"):
                        try:
                            next_url = urljoin(str(resp.url), redirect_target)
                            resp2 = await client.get(next_url, headers=headers)
                            if resp2.status_code == 200:
                                text2 = decode_html(resp2.content, resp2.headers.get("content-type", ""))
                                if len(text2) > 250 and "<a" in text2.lower():
                                    return text2, str(resp2.url)
                        except Exception:
                            pass
                
                # Check for explicit client-side anti-bot WAF challenge splash
                text_low = text.lower()
                if any(w in text_low for w in ("waf", "challenge", "captcha", "security check", "安全验证", "防火墙", "antispider", "browser check")):
                    logger.info(f"[{uni_name}] Client-side WAF challenge detected in HTML on {url}; engaging Headless Playwright...")
                    waf_blocked = True
            elif resp.status_code in (403, 412, 429, 521):
                logger.info(f"[{uni_name}] HTTP {resp.status_code} WAF challenge on {url}; engaging Headless Playwright browser...")
                waf_blocked = True
        except Exception as e:
            # Strictly do NOT engage Playwright on timeouts, DNS errors, or dead hosts
            logger.debug(f"[{uni_name}] Fast HTTP probe failed on {url}: {e}")
            waf_blocked = False

        if waf_blocked and allow_playwright:
            try:
                html, final_url = await harvester.fetch_html_dynamic(url)
                if html and len(html) > 250:
                    logger.info(f"[{uni_name}] ✓ Headless Playwright bypassed WAF / rendered {final_url}")
                    return html, final_url
            except Exception as pw_err:
                logger.warning(f"[{uni_name}] Headless Playwright fallback failed on {url}: {pw_err}")

        return None, None

    async def resolve_department_from_homepage(
        self,
        university: University,
        discipline: str = "Computer Science"
    ) -> University:
        """
        Two-Stage Homepage-First Department & Supervisor Discovery:
        - Step 1: Probes the candidate university homepage (with www., meta-refresh, and 1-at-a-time Playwright WAF fallback).
          Marks 'website_verified = True' as soon as Step 1 succeeds!
        - Step 2: Follows '院系设置' / '机构设置' or probes real CS/AI subdomains in parallel.
          If Step 1 succeeds and Step 2 fails, preserves the verified homepage ('Homepage OK · Dept Not Found')
          instead of marking the whole university failed!
        """
        import asyncio
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

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

        candidates_root = []
        if university.website:
            candidates_root.append(university.website)
        for cand in (
            f"https://www.{university.domain}/",
            f"http://www.{university.domain}/",
            f"https://{university.domain}/",
            f"http://{university.domain}/"
        ):
            if cand not in candidates_root:
                candidates_root.append(cand)

        homepage_html = None
        working_root = None
        playwright_used = False

        logger.info(f"[{university.name}] [Step 1/2] Live probing homepage ({candidates_root[0]})...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(timeout=6.5, follow_redirects=True, verify=False) as client:
            for root_url in candidates_root:
                # Allow Playwright fallback once per university if an authentic WAF code (403, 412, 429, 521) is encountered
                html, final_u = await self._fetch_with_waf_fallback(
                    client, root_url, headers, university.name, allow_playwright=(not playwright_used)
                )
                if not playwright_used and not html:
                    # Mark playwright as attempted if an actual WAF challenge occurred
                    pass
                if html and final_u:
                    homepage_html = html
                    working_root = final_u
                    university.website = working_root
                    university.website_verified = True
                    university.verified_at = datetime.now(timezone.utc)
                    university.pipeline_status = "Homepage Verified"
                    logger.info(f"[{university.name}] [Step 1/2 ✓] Live Homepage Verified at {working_root}")
                    break

            # Discipline-Adaptive Department Keywords with Rich Chinese Higher-Ed Taxonomy
            disc_lower = (discipline or "").lower()
            dept_keywords = [
                "计算机", "人工智能", "软件", "数计", "数学与计算机", "信息工程", "信息科学",
                "智能科学", "网络空间", "大数据", "物联网", "网络工程", "数据科学", "电子信息",
                "计算机科学与技术", "智能与计算", "计算学院", "大数据与软件",
                "computer", "artificial intelligence", "software", "informatics", "computing"
            ]
            if "artif" in disc_lower or "ai" in disc_lower:
                dept_keywords = [
                    "人工智能", "智能科学与技术", "智能科学", "智能工程", "机器人", "自动化",
                    "机器智能", "智能控制", "模式识别", "ai", "artificial intelligence", "robotics"
                ] + dept_keywords
            elif "soft" in disc_lower:
                dept_keywords = [
                    "软件", "软件工程", "网络空间安全", "信息安全", "保密学院", "网络安全",
                    "software", "cyber", "information security"
                ] + dept_keywords

            unit_suffixes = ["学院", "系", "学部", "研究院", "重点实验室", "中心", "school", "college", "department", "faculty"]
            nav_keywords = [
                "院系设置", "机构设置", "教学单位", "学院设置", "二级学院", "学部院系",
                "院系总览", "学院导航", "教学机构", "院系所", "教学与科研", "学科建设",
                "教学科研单位", "学校机构", "组织机构", "教育教学"
            ]
            news_exclude_keywords = ["活动", "通知", "公告", "新闻", "讲座", "招聘", "公示", "大赛", "会议", "党支部", "获批", "举行", "开展", "圆满", "喜报"]
            auth_url_exclusions = ["login", "authserver", "webvpn", "clientvpn", "cas", "sso", "passport", "portal", "userlogin"]
            auth_title_exclusions = ["统一身份认证", "用户登录", "系统登录", "认证中心", "vpn登录", "单点登录"]

            def _is_valid_dept_link(text_str: str, url_str: str) -> bool:
                t_clean = (text_str or "").strip()
                t_low = t_clean.lower()
                u_low = (url_str or "").lower()
                # Accept up to 34 characters to allow standard parenthetical Chinese college names
                # e.g. 计算机科学与技术学院（示范性软件学院）
                if not t_clean or len(t_clean) > 34:
                    return False
                if any(nk in u_low for nk in ("/info/", "/news/", "/content/", "/article/", "/notice/")):
                    return False
                if any(ak in u_low for ak in auth_url_exclusions):
                    return False
                if any(at in t_low for at in auth_title_exclusions):
                    return False
                if any(nk in t_low for nk in news_exclude_keywords):
                    return False
                has_kw = any(k in t_low for k in dept_keywords)
                has_unit = any(u in t_low for u in unit_suffixes)
                return has_kw and has_unit

            discovered_depts = []
            nav_links = []

            if homepage_html and working_root:
                soup = BeautifulSoup(homepage_html, "html.parser")
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True)
                    full_url = _safe_urljoin(working_root, a.get("href", ""))
                    if not text or not full_url:
                        continue
                    if any(nk in text for nk in nav_keywords) and len(text) <= 15:
                        nav_links.append((text, full_url))
                    elif _is_valid_dept_link(text, full_url):
                        discovered_depts.append((text, full_url))

                # Step 2a: Follow '院系设置' (Schools Directory) to get official school links
                if nav_links:
                    nav_links.sort(key=lambda x: 0 if "院系" in x[0] or "学院" in x[0] else 1)
                    # Inspect up to 2 school directory nav links if the first one doesn't yield departments
                    for nav_text, nav_url in nav_links[:2]:
                        logger.info(f"[{university.name}] [Step 2/2] Following Schools Directory '{nav_text}' -> {nav_url}")
                        nav_html, nav_final_url = await self._fetch_with_waf_fallback(
                            client, nav_url, headers, university.name, allow_playwright=False
                        )
                        if nav_html and nav_final_url:
                            nav_soup = BeautifulSoup(nav_html, "html.parser")
                            for a in nav_soup.find_all("a", href=True):
                                t = a.get_text(strip=True)
                                f_url = _safe_urljoin(nav_final_url, a.get("href", ""))
                                if t and f_url and _is_valid_dept_link(t, f_url):
                                    discovered_depts.append((t, f_url))
                        if discovered_depts:
                            break

            # Fallback Step 2b: If main homepage used JS menus or was WAF-locked, probe verified CS/Info college subdomains concurrently!
            if not discovered_depts:
                logger.info(f"[{university.name}] [Step 2/2] Probing CS/AI college subdomains in parallel on {university.domain}...")
                
                # Comprehensive Chinese higher-ed departmental subdomain patterns
                subdomain_candidates = [
                    ("cs", "School of Computer Science"),
                    ("cst", "School of Computer Science & Technology"),
                    ("ai", "School of Artificial Intelligence"),
                    ("cist", "College of Computer Science & Cyber Security"),
                    ("jsj", "School of Computer Science (计算机学院)"),
                    ("scse", "School of Computer Science & Engineering"),
                    ("sist", "School of Information Science & Technology"),
                    ("cie", "College of Information Engineering"),
                    ("ccst", "College of Computer Science and Technology"),
                    ("se", "School of Software Engineering"),
                    ("soft", "School of Software"),
                    ("sse", "School of Software Engineering"),
                    ("csit", "School of Computer Science & Information Technology"),
                    ("scs", "School of Computer Science"),
                    ("eecs", "School of Electronics Engineering & Computer Science"),
                    ("cyber", "School of Cyber Science and Engineering"),
                    ("inf", "School of Informatics"),
                    ("it", "School of Information Technology"),
                ]

                # Weight AI or Software subdomains higher if user targeted that discipline
                if "artif" in disc_lower or "ai" in disc_lower:
                    subdomain_candidates.sort(key=lambda x: 0 if x[0] in ("ai", "sai", "auto") else 1)
                elif "soft" in disc_lower:
                    subdomain_candidates.sort(key=lambda x: 0 if x[0] in ("se", "soft", "sse") else 1)

                async def _probe_sub(prefix: str, label: str):
                    for scheme in ("https", "http"):
                        sub_url = f"{scheme}://{prefix}.{university.domain}/"
                        s_html, s_final = await self._fetch_with_waf_fallback(
                            client, sub_url, headers, university.name, allow_playwright=False
                        )
                        if s_html and s_final:
                            s_final_low = s_final.lower()
                            if any(ak in s_final_low for ak in auth_url_exclusions):
                                return None
                            s_soup = BeautifulSoup(s_html, "html.parser")
                            t_text = s_soup.title.get_text(strip=True) if s_soup.title else label
                            t_text_low = t_text.lower()
                            if any(at in t_text_low for at in auth_title_exclusions):
                                return None
                            return (t_text or label, s_final)
                    return None

                sub_results = await asyncio.gather(*[_probe_sub(p, lbl) for p, lbl in subdomain_candidates], return_exceptions=True)
                for res_item in sub_results:
                    if isinstance(res_item, tuple) and len(res_item) == 2:
                        title_text, sub_final = res_item
                        discovered_depts.append((title_text, sub_final))
                        university.website_verified = True
                        university.verified_at = datetime.now(timezone.utc)
                        if not working_root:
                            working_root = f"https://www.{university.domain}/"
                        logger.info(f"[{university.name}] [Step 2/2 ✓] Live-verified CS/AI Subdomain: {title_text} -> {sub_final}")
                        break

            if not discovered_depts:
                if not university.website_verified:
                    university.pipeline_status = "Step 1 Failed: Homepage Unreachable"
                    university.status_reason = (
                        f"Step 1 Failed: Homepage ({university.website or university.domain}) and CS/AI subdomains "
                        f"timed out, failed DNS, or were blocked by WAF."
                    )
                    university.department_endpoints = [
                        DepartmentEndpoint(
                            name="Institutional Homepage (Step 1 Unreachable)",
                            url=university.website or f"https://www.{university.domain}/",
                            is_verified=False,
                            status="Step 1 Failed: Homepage Unreachable"
                        )
                    ]
                    logger.warning(f"[{university.name}] [Step 1/2 ✗] {university.status_reason}")
                else:
                    # Step 1 (Homepage) SUCCEEDED! Only Step 2 (Department) did not find a static CS/AI link.
                    university.pipeline_status = "Homepage OK · Dept Not Found"
                    university.status_reason = (
                        f"Step 1 Succeeded (Homepage OK at {working_root}) | Step 2 Dept Not Found: "
                        f"No static CS/AI link matched in '院系设置' or common subdomains."
                    )
                    university.department_endpoints = [
                        DepartmentEndpoint(
                            name="🏛️ Verified Institutional Homepage (Step 1 OK)",
                            url=working_root,
                            is_verified=True,
                            status="Homepage Verified"
                        )
                    ]
                    logger.warning(f"[{university.name}] [Step 1/2 ✓ | Step 2/2 ⚠] {university.status_reason}")
                return university

            # Deduplicate discovered department links
            unique_depts = []
            seen_u = set()
            for d_name, d_url in discovered_depts:
                if d_url not in seen_u:
                    seen_u.add(d_url)
                    unique_depts.append((d_name, d_url))

            university.pipeline_status = "Department URL Found"
            university.status_reason = f"Step 1 Homepage OK ({working_root}) & Step 2 CS/AI Dept Resolved ({unique_depts[0][1]})."
            university.resolved_at = datetime.now(timezone.utc)

            # Always preserve the Verified Institutional Homepage (Step 1) as the first endpoint!
            final_endpoints: List[DepartmentEndpoint] = []
            if working_root:
                final_endpoints.append(DepartmentEndpoint(
                    name="🏛️ Verified Institutional Homepage (Step 1 OK)",
                    url=working_root,
                    is_verified=True,
                    status="Homepage Verified"
                ))

            faculty_keywords = [
                "导师队伍", "研究生导师", "硕士生导师", "博士生导师", "硕导", "博导",
                "师资队伍", "教师名录", "师资力量", "教师队伍", "师资概况", "专任教师",
                "教授名录", "副教授名录", "导师介绍", "导师信息", "硕导名单", "博导名单",
                "学术队伍", "教师简介", "教师主页", "师资介绍", "人员概况", "教职工",
                "硕士导师", "博士导师", "博导名录", "硕导名录", "导师名录", "指导教师",
                "学术骨干", "骨干教师", "学者名录", "教授", "副教授",
                "faculty", "supervisors", "professors", "people", "academic staff"
            ]

            # Step 3: Inspect top 3 matched departments for '师资队伍' / '导师队伍'
            for d_name, d_url in unique_depts[:3]:
                logger.info(f"[{university.name}] [Step 2/2 ✓] Department found '{d_name}' -> {d_url}. Checking for supervisor roster...")
                found_faculty_page = False
                d_html, d_final_url = await self._fetch_with_waf_fallback(
                    client, d_url, headers, university.name, allow_playwright=False
                )
                if d_html and d_final_url:
                    d_soup = BeautifulSoup(d_html, "html.parser")
                    for a in d_soup.find_all("a", href=True):
                        ft = a.get_text(strip=True)
                        fac_url = _safe_urljoin(d_final_url, a.get("href", ""))
                        if ft and fac_url and any(fk in ft.lower() for fk in faculty_keywords) and len(ft) <= 25:
                            final_endpoints.append(DepartmentEndpoint(
                                name=f"👨‍🏫 {d_name} ({ft})",
                                url=fac_url,
                                is_verified=True,
                                status="Faculty Page Found"
                            ))
                            university.pipeline_status = "Faculty Page Found"
                            university.status_reason = f"Step 1 Homepage OK & Step 2 CS/AI Dept + Supervisor Roster Verified ({fac_url})."
                            found_faculty_page = True
                            logger.info(f"[{university.name}] [Step 2/2 ✓] Verified Supervisor Roster '{ft}' -> {fac_url}")
                            break

                if not found_faculty_page:
                    final_endpoints.append(DepartmentEndpoint(
                        name=f"🎓 {d_name}",
                        url=d_url,
                        is_verified=True,
                        status="Department URL Found"
                    ))

            if final_endpoints:
                university.department_endpoints = final_endpoints

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
