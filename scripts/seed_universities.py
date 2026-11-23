"""Curated China university rankings seed loader and filter query helper."""

import asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import mongo_manager
from app.db.repositories import Repository
from app.schemas.entities import UniversitySeed
from app.schemas.filters import parse_tier_limit

CURATED_CHINA_UNIVERSITIES: list[UniversitySeed] = [
    UniversitySeed(domain="tsinghua.edu.cn", name="Tsinghua University", chinese_name="清华大学", country="China", region="Beijing", rank=1),
    UniversitySeed(domain="pku.edu.cn", name="Peking University", chinese_name="北京大学", country="China", region="Beijing", rank=2),
    UniversitySeed(domain="zju.edu.cn", name="Zhejiang University", chinese_name="浙江大学", country="China", region="Zhejiang", rank=3),
    UniversitySeed(domain="sjtu.edu.cn", name="Shanghai Jiao Tong University", chinese_name="上海交通大学", country="China", region="Shanghai", rank=4),
    UniversitySeed(domain="fudan.edu.cn", name="Fudan University", chinese_name="复旦大学", country="China", region="Shanghai", rank=5),
    UniversitySeed(domain="nju.edu.cn", name="Nanjing University", chinese_name="南京大学", country="China", region="Jiangsu", rank=6),
    UniversitySeed(domain="ustc.edu.cn", name="University of Science and Technology of China", chinese_name="中国科学技术大学", country="China", region="Anhui", rank=7),
    UniversitySeed(domain="hit.edu.cn", name="Harbin Institute of Technology", chinese_name="哈尔滨工业大学", country="China", region="Heilongjiang", rank=8),
    UniversitySeed(domain="buaa.edu.cn", name="Beihang University", chinese_name="北京航空航天大学", country="China", region="Beijing", rank=9),
    UniversitySeed(domain="hust.edu.cn", name="Huazhong University of Science and Technology", chinese_name="华中科技大学", country="China", region="Hubei", rank=10),
    UniversitySeed(domain="whu.edu.cn", name="Wuhan University", chinese_name="武汉大学", country="China", region="Hubei", rank=11),
    UniversitySeed(domain="xjtu.edu.cn", name="Xi'an Jiaotong University", chinese_name="西安交通大学", country="China", region="Shaanxi", rank=12),
    UniversitySeed(domain="sysu.edu.cn", name="Sun Yat-sen University", chinese_name="中山大学", country="China", region="Guangdong", rank=13),
    UniversitySeed(domain="seu.edu.cn", name="Southeast University", chinese_name="东南大学", country="China", region="Jiangsu", rank=14),
    UniversitySeed(domain="tongji.edu.cn", name="Tongji University", chinese_name="同济大学", country="China", region="Shanghai", rank=15),
    UniversitySeed(domain="uestc.edu.cn", name="University of Electronic Science and Technology of China", chinese_name="电子科技大学", country="China", region="Sichuan", rank=16),
    UniversitySeed(domain="scu.edu.cn", name="Sichuan University", chinese_name="四川大学", country="China", region="Sichuan", rank=17),
    UniversitySeed(domain="nwpu.edu.cn", name="Northwestern Polytechnical University", chinese_name="西北工业大学", country="China", region="Shaanxi", rank=18),
    UniversitySeed(domain="bit.edu.cn", name="Beijing Institute of Technology", chinese_name="北京理工大学", country="China", region="Beijing", rank=19),
    UniversitySeed(domain="nankai.edu.cn", name="Nankai University", chinese_name="南开大学", country="China", region="Tianjin", rank=20),
]


async def seed_universities(db: AsyncIOMotorDatabase) -> int:
    """Idempotently upserts all curated China universities into `universities_seed`."""
    repo = Repository(db)
    for seed in CURATED_CHINA_UNIVERSITIES:
        await repo.upsert_university_seed(seed)
    return len(CURATED_CHINA_UNIVERSITIES)


async def filter_university_seeds(
    db: AsyncIOMotorDatabase,
    *,
    country: str = "China",
    regions: list[str] | None = None,
    tier: str | None = "top_10",
    limit: int | None = None,
) -> list[UniversitySeed]:
    """Queries seeded universities sorted by rank ascending with region and tier/limit filters."""
    repo = Repository(db)
    eff_limit = limit if limit is not None else parse_tier_limit(tier)
    return await repo.query_university_seeds(country=country, regions=regions or None, limit=eff_limit)


async def _main() -> None:
    db = await mongo_manager.connect()
    count = await seed_universities(db)
    print(f"Seeded {count} universities into {mongo_manager.db_name}.universities_seed")
    await mongo_manager.close()


if __name__ == "__main__":
    asyncio.run(_main())
