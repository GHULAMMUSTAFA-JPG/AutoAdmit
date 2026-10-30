"""Generates comprehensive Chinese Universities metadata catalog."""

import json
import os

catalog = {
    # BEIJING
    "tsinghua.edu.cn": {
        "name": "Tsinghua University",
        "chinese_name": "清华大学",
        "region": "Beijing",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 1,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 1 Dream. Strict academic cutoffs. Focus outreach toward early-career faculty / Associate Professors and new engineering labs requiring hands-on output."
    },
    "pku.edu.cn": {
        "name": "Peking University",
        "chinese_name": "北京大学",
        "region": "Beijing",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 2,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 1 Dream. Top national AI labs and software engineering centers."
    },
    "buaa.edu.cn": {
        "name": "Beihang University",
        "chinese_name": "北京航空航天大学",
        "region": "Beijing",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 8,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985/211 engineering powerhouse. High interest in applied systems and robotics."
    },
    "bit.edu.cn": {
        "name": "Beijing Institute of Technology",
        "chinese_name": "北京理工大学",
        "region": "Beijing",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 9,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship", "Belt and Road Scholarship"],
        "feasibility_notes": "Tier 1 Dream. Premier national engineering key institution with high research output in intelligent control."
    },
    "bupt.edu.cn": {
        "name": "Beijing Univ of Posts and Telecommunications",
        "chinese_name": "北京邮电大学",
        "region": "Beijing",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 10,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Known as China's Silicon Valley cradle for telecommunications and software engineering."
    },
    "bjtu.edu.cn": {
        "name": "Beijing Jiaotong University",
        "chinese_name": "北京交通大学",
        "region": "Beijing",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 15,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 key engineering hub. Receptive to hands-on software development candidates."
    },
    "ustb.edu.cn": {
        "name": "University of Science and Technology Beijing",
        "chinese_name": "北京科技大学",
        "region": "Beijing",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 25,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. High international student quota and established computer science laboratories."
    },
    "bjut.edu.cn": {
        "name": "Beijing University of Technology",
        "chinese_name": "北京工业大学",
        "region": "Beijing",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 32,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Beijing Municipal Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Major Beijing municipal tech institute with strong applied AI departments."
    },
    "ncepu.edu.cn": {
        "name": "North China Electric Power University",
        "chinese_name": "华北电力大学",
        "region": "Beijing",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 38,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 National Key. Strong focus on smart grid IoT and energy computation."
    },
    "ucas.edu.cn": {
        "name": "University of Chinese Academy of Sciences",
        "chinese_name": "中国科学院大学",
        "region": "Beijing",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 6,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["ANSO Scholarship for Young Talents", "CAS-TWAS President's Fellowship", "CSC Type B (Full Funding)"],
        "feasibility_notes": "Tier 1 Dream. Highest density of CAS research institutes and massive full fellowship allocations (ANSO/CAS-TWAS)."
    },

    # SHANGHAI
    "sjtu.edu.cn": {
        "name": "Shanghai Jiao Tong University",
        "chinese_name": "上海交通大学",
        "region": "Shanghai",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 4,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "Shanghai Government Scholarship (SGS)"],
        "feasibility_notes": "Tier 1 Dream. Top international reputation with dedicated Institute of Artificial Intelligence."
    },
    "fudan.edu.cn": {
        "name": "Fudan University",
        "chinese_name": "复旦大学",
        "region": "Shanghai",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 5,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "Shanghai Government Scholarship (SGS)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 1 Dream. Elite C9 institution with top NLP and systems laboratories."
    },
    "tongji.edu.cn": {
        "name": "Tongji University",
        "chinese_name": "同济大学",
        "region": "Shanghai",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 12,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "Shanghai Government Scholarship (SGS)"],
        "feasibility_notes": "Tier 1 Dream. Project 985 powerhouse in smart systems and autonomous driving."
    },
    "ecnu.edu.cn": {
        "name": "East China Normal University",
        "chinese_name": "华东师范大学",
        "region": "Shanghai",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 16,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Shanghai Government Scholarship (SGS)"],
        "feasibility_notes": "Tier 2 Target. Project 985 with high internationalization and state key labs in software engineering."
    },
    "shu.edu.cn": {
        "name": "Shanghai University",
        "chinese_name": "上海大学",
        "region": "Shanghai",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 28,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "Shanghai Government Scholarship (SGS)"],
        "feasibility_notes": "Tier 2 Target. Fast-rising tech hub with generous Shanghai municipal funding."
    },
    "ecust.edu.cn": {
        "name": "East China Univ of Science and Technology",
        "chinese_name": "华东理工大学",
        "region": "Shanghai",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 34,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "Shanghai Government Scholarship (SGS)"],
        "feasibility_notes": "Tier 2 Target. Project 211 key engineering university with active computer systems labs."
    },
    "shanghaitech.edu.cn": {
        "name": "ShanghaiTech University",
        "chinese_name": "上海科技大学",
        "region": "Shanghai",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 22,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["Full University Fellowship", "CSC Type B (Full Funding)"],
        "feasibility_notes": "Tier 2 Target. Cutting-edge research institute partnering with CAS. Fully English-speaking faculty."
    },

    # ZHEJIANG
    "zju.edu.cn": {
        "name": "Zhejiang University",
        "chinese_name": "浙江大学",
        "region": "Zhejiang",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 3,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "Zhejiang Provincial Government Scholarship", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 1 Dream. College of Computer Science & Technology labs working on vision and robotics."
    },
    "hdu.edu.cn": {
        "name": "Hangzhou Dianzi University",
        "chinese_name": "杭州电子科技大学",
        "region": "Zhejiang",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 29,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Zhejiang Provincial Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Renowned electronic/IT powerhouse with direct ties to Alibaba and tech industry."
    },
    "nbu.edu.cn": {
        "name": "Ningbo University",
        "chinese_name": "宁波大学",
        "region": "Zhejiang",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 50,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Ningbo Municipal Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Double First-Class institution with high acceptance rate and full funding opportunities."
    },

    # JIANGSU
    "nju.edu.cn": {
        "name": "Nanjing University",
        "chinese_name": "南京大学",
        "region": "Jiangsu",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 5,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "Jasmine Jiangsu Government Scholarship"],
        "feasibility_notes": "Tier 1 Dream. National Key Lab for Novel Software Technology. High prestige in AI theory."
    },
    "seu.edu.cn": {
        "name": "Southeast University",
        "chinese_name": "东南大学",
        "region": "Jiangsu",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 11,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Jasmine Jiangsu Government Scholarship"],
        "feasibility_notes": "Tier 1 Dream. Top engineering school in eastern China with massive CS and networking research."
    },
    "nuaa.edu.cn": {
        "name": "Nanjing Univ of Aeronautics and Astronautics",
        "chinese_name": "南京航空航天大学",
        "region": "Jiangsu",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 20,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 key engineering hub. Strong pattern recognition and AI groups."
    },
    "njust.edu.cn": {
        "name": "Nanjing Univ of Science and Technology",
        "chinese_name": "南京理工大学",
        "region": "Jiangsu",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 21,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "Jasmine Jiangsu Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211. Receptive to international computer science scholars."
    },
    "suda.edu.cn": {
        "name": "Soochow University",
        "chinese_name": "苏州大学",
        "region": "Jiangsu",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 33,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "Jasmine Jiangsu Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Fast-growing comprehensive Project 211 in Suzhou's vibrant industrial park."
    },
    "nuist.edu.cn": {
        "name": "Nanjing Univ. of Information Science & Tech",
        "chinese_name": "南京信息工程大学",
        "region": "Jiangsu",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 35,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Jasmine Jiangsu Government Scholarship", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 3 Safety. High international graduate quotas and full scholarship grants (Jasmine / CSC). High admission probability."
    },
    "jiangnan.edu.cn": {
        "name": "Jiangnan University",
        "chinese_name": "江南大学",
        "region": "Jiangsu",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 42,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Jasmine Jiangsu Government Scholarship", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Project 211 with accessible admission minimums, 0 application fee, and high acceptance of external CSC candidates."
    },
    "njupt.edu.cn": {
        "name": "Nanjing Univ of Posts and Telecommunications",
        "chinese_name": "南京邮电大学",
        "region": "Jiangsu",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 26,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Jasmine Jiangsu Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Double First-Class specialty institution in telecom, big data, and cybersecurity."
    },

    # SHAANXI
    "xjtu.edu.cn": {
        "name": "Xi'an Jiaotong University",
        "chinese_name": "西安交通大学",
        "region": "Shaanxi",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 10,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. C9 League institution with large AI research institute."
    },
    "xidian.edu.cn": {
        "name": "Xidian University",
        "chinese_name": "西安电子科技大学",
        "region": "Shaanxi",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 12,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Belt and Road Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 National Key. Zero application fee barrier. Strong alignment with AI & signals."
    },
    "nwpu.edu.cn": {
        "name": "Northwestern Polytechnical University",
        "chinese_name": "西北工业大学",
        "region": "Shaanxi",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 13,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "Belt and Road Scholarship", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 1 Dream. Project 985 top engineering hub with world-class computer vision and automation."
    },
    "nwu.edu.cn": {
        "name": "Northwest University",
        "chinese_name": "西北大学",
        "region": "Shaanxi",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 37,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Shaanxi Provincial Scholarship"],
        "feasibility_notes": "Tier 2 Target. Historic Project 211 institution with active computer science and software faculties."
    },
    "chd.edu.cn": {
        "name": "Chang'an University",
        "chinese_name": "长安大学",
        "region": "Shaanxi",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 52,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Project 211 with high admission accessibility and strong intelligent transportation labs."
    },

    # HUBEI
    "hust.edu.cn": {
        "name": "Huazhong Univ. of Science and Technology",
        "chinese_name": "华中科技大学",
        "region": "Hubei",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 7,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 top engineering hub in central China."
    },
    "whu.edu.cn": {
        "name": "Wuhan University",
        "chinese_name": "武汉大学",
        "region": "Hubei",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 14,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 1 Dream. Comprehensive Project 985 university with major computer vision research."
    },
    "whut.edu.cn": {
        "name": "Wuhan University of Technology",
        "chinese_name": "武汉理工大学",
        "region": "Hubei",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 27,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "Hubei Provincial Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 key engineering university with high international enrollment."
    },

    # GUANGDONG
    "sysu.edu.cn": {
        "name": "Sun Yat-sen University",
        "chinese_name": "中山大学",
        "region": "Guangdong",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 13,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": ["CSC Type B (Full Funding)", "Guangdong Provincial Government Scholarship", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Top southern comprehensive university with major AI School in Shenzhen campus."
    },
    "scut.edu.cn": {
        "name": "South China University of Technology",
        "chinese_name": "华南理工大学",
        "region": "Guangdong",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 17,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "Guangdong Provincial Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 powerhouse in Guangzhou and Greater Bay Area technology ecosystem."
    },
    "szu.edu.cn": {
        "name": "Shenzhen University",
        "chinese_name": "深圳大学",
        "region": "Guangdong",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 24,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["Shenzhen Universiade Scholarship", "CSC Type B (Full Funding)", "Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Massive research endowments, modern AI institutes, and top placement in Tencent and Huawei."
    },
    "sustech.edu.cn": {
        "name": "Southern Univ of Science and Technology",
        "chinese_name": "南方科技大学",
        "region": "Guangdong",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 19,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["SUSTech Presidential Fellowship", "CSC Type B (Full Funding)"],
        "feasibility_notes": "Tier 1 Dream. High-stipend global research university with English teaching and world-class faculty."
    },
    "gdut.edu.cn": {
        "name": "Guangdong University of Technology",
        "chinese_name": "广东工业大学",
        "region": "Guangdong",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 43,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Guangdong Provincial Government Scholarship"],
        "feasibility_notes": "Tier 3 Safety. High admissions accessibility and extensive industry engineering partnerships."
    },

    # SICHUAN & CHONGQING
    "uestc.edu.cn": {
        "name": "Univ. of Electronic Science & Tech of China",
        "chinese_name": "电子科技大学",
        "region": "Sichuan",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 11,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 420,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Outstanding CS/AI research facilities and high quota for international researchers."
    },
    "scu.edu.cn": {
        "name": "Sichuan University",
        "chinese_name": "四川大学",
        "region": "Sichuan",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 23,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "Sichuan Provincial Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 key comprehensive institution with strong biological computing and AI labs."
    },
    "swjtu.edu.cn": {
        "name": "Southwest Jiaotong University",
        "chinese_name": "西南交通大学",
        "region": "Sichuan",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 31,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 key university with active intelligent systems and software programs."
    },
    "cqu.edu.cn": {
        "name": "Chongqing University",
        "chinese_name": "重庆大学",
        "region": "Chongqing",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 26,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Chongqing Municipal Mayor Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 in southwestern municipality with large faculty hiring campaigns."
    },
    "cqupt.edu.cn": {
        "name": "Chongqing Univ of Posts and Telecommunications",
        "chinese_name": "重庆邮电大学",
        "region": "Chongqing",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 37,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Chongqing Municipal Mayor Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Highly respected telecommunications and computer science powerhouse with generous scholarships."
    },

    # HEILONGJIANG, JILIN & LIAONING
    "hit.edu.cn": {
        "name": "Harbin Institute of Technology",
        "chinese_name": "哈尔滨工业大学",
        "region": "Heilongjiang",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 9,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Outstanding CS faculty with high quota for research scholars in NLP and automation."
    },
    "hrbeu.edu.cn": {
        "name": "Harbin Engineering University",
        "chinese_name": "哈尔滨工程大学",
        "region": "Heilongjiang",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 30,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 key technology university with strong cyber defense and systems engineering."
    },
    "jlu.edu.cn": {
        "name": "Jilin University",
        "chinese_name": "吉林大学",
        "region": "Jilin",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 21,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Large Project 985 university with comprehensive AI and computer science programs."
    },
    "dlut.edu.cn": {
        "name": "Dalian University of Technology",
        "chinese_name": "大连理工大学",
        "region": "Liaoning",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 22,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 coastal engineering center with strong machine learning labs."
    },
    "neu.edu.cn": {
        "name": "Northeastern University",
        "chinese_name": "东北大学",
        "region": "Liaoning",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 19,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "Liaoning Provincial Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Pioneer of industrial automation and software systems in China."
    },

    # ANHUI & JIANGXI
    "ustc.edu.cn": {
        "name": "Univ of Science and Technology of China",
        "chinese_name": "中国科学技术大学",
        "region": "Anhui",
        "tier": "Tier 1 (Dream)",
        "cs_ranking": 6,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "USTC Fellowship", "CAS-TWAS President's Fellowship"],
        "feasibility_notes": "Tier 1 Dream. C9 League elite science institution known for theoretical rigor and quantum/AI breakthroughs."
    },
    "hfut.edu.cn": {
        "name": "Hefei University of Technology",
        "chinese_name": "合肥工业大学",
        "region": "Anhui",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 35,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 211 key automotive and computer engineering institute."
    },
    "ncu.edu.cn": {
        "name": "Nanchang University",
        "chinese_name": "南昌大学",
        "region": "Jiangxi",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 45,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Jiangxi Provincial Government Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Project 211 flagship institution in central China with accessible acceptance thresholds."
    },

    # SHANDONG & HENAN
    "sdu.edu.cn": {
        "name": "Shandong University",
        "chinese_name": "山东大学",
        "region": "Shandong",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 16,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Shandong Provincial Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 institution with leading cryptographic and software engineering institutes."
    },
    "ouc.edu.cn": {
        "name": "Ocean University of China",
        "chinese_name": "中国海洋大学",
        "region": "Shandong",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 41,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 located in Qingdao with active marine informatics and big data labs."
    },
    "zzu.edu.cn": {
        "name": "Zhengzhou University",
        "chinese_name": "郑州大学",
        "region": "Henan",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 39,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Henan Provincial Government Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Double First-Class mega-university with extensive funding and high international quotas."
    },

    # HUNAN & FUJIAN
    "csu.edu.cn": {
        "name": "Central South University",
        "chinese_name": "中南大学",
        "region": "Hunan",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 15,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 powerhouse in medical informatics and big data architectures."
    },
    "hnu.edu.cn": {
        "name": "Hunan University",
        "chinese_name": "湖南大学",
        "region": "Hunan",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 20,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Hunan Provincial Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 National Supercomputing Center host university."
    },
    "xmu.edu.cn": {
        "name": "Xiamen University",
        "chinese_name": "厦门大学",
        "region": "Fujian",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 25,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Fujian Provincial Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 coastal institution with distinguished AI and computer vision faculty."
    },
    "fzu.edu.cn": {
        "name": "Fuzhou University",
        "chinese_name": "福州大学",
        "region": "Fujian",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 38,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Project 211 key engineering university with high graduate scholarship quotas."
    },

    # TIANJIN
    "nankai.edu.cn": {
        "name": "Nankai University",
        "chinese_name": "南开大学",
        "region": "Tianjin",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 24,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": ["CSC Type B (Full Funding)", "Tianjin Municipal Government Scholarship"],
        "feasibility_notes": "Tier 2 Target. Prestigious Project 985 with prominent artificial intelligence and software colleges."
    },
    "tju.edu.cn": {
        "name": "Tianjin University",
        "chinese_name": "天津大学",
        "region": "Tianjin",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 18,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 420,
        "scholarships": ["CSC Type B (Full Funding)", "Tianjin Municipal Government Scholarship", "Peiyang Scholarship"],
        "feasibility_notes": "Tier 2 Target. Oldest modern university in China, Project 985 engineering leader."
    },

    # OTHER MAJOR REGIONS (GANSU, GUANGXI, YUNNAN, SHANXI, XINJIANG)
    "lzu.edu.cn": {
        "name": "Lanzhou University",
        "chinese_name": "兰州大学",
        "region": "Gansu",
        "tier": "Tier 2 (Target)",
        "cs_ranking": 33,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": ["CSC Type B (Full Funding)", "Belt and Road Scholarship", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 2 Target. Project 985 with high international fellowship allocation along the Silk Road."
    },
    "guet.edu.cn": {
        "name": "Guilin Univ of Electronic Technology",
        "chinese_name": "桂林电子科技大学",
        "region": "Guangxi",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 41,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Guangxi Government ASEAN Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Highly specialized IT & electronics institution with zero fee and high admission probability."
    },
    "gxu.edu.cn": {
        "name": "Guangxi University",
        "chinese_name": "广西大学",
        "region": "Guangxi",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 50,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Guangxi Government ASEAN Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Project 211 key university with large quotas for international researchers."
    },
    "ynu.edu.cn": {
        "name": "Yunnan University",
        "chinese_name": "云南大学",
        "region": "Yunnan",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 47,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Yunnan Provincial Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Double First-Class Project 211 university with friendly graduate admission policies."
    },
    "tyut.edu.cn": {
        "name": "Taiyuan University of Technology",
        "chinese_name": "太原理工大学",
        "region": "Shanxi",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 44,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "University Presidential Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Project 211 engineering university with strong high-performance computing centers."
    },
    "xju.edu.cn": {
        "name": "Xinjiang University",
        "chinese_name": "新疆大学",
        "region": "Xinjiang",
        "tier": "Tier 3 (Safety)",
        "cs_ranking": 55,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": ["CSC Type B (Full Funding)", "Belt and Road Scholarship"],
        "feasibility_notes": "Tier 3 Safety. Double First-Class Project 211 with high Silk Road scholarship grants."
    }
}

target_path = os.path.join("src", "data", "chinese_universities.json")
with open(target_path, "w", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)

print(f"Successfully generated {len(catalog)} universities in {target_path}")
