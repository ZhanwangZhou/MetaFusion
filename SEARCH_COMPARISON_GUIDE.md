# MetaFusion搜索方法对比指南

本指南说明如何使用MetaFusion系统进行三种搜索方法的准确度对比测试。

## 三种搜索方法

### 1. MetaFusion搜索（元数据过滤 + 向量搜索）
- **位置**: Leader节点元数据过滤 + 选定的Follower节点向量搜索
- **描述**: 先在Leader节点使用元数据（时间、位置等）过滤候选silos，然后只在这些候选silos上进行向量搜索
- **优势**: 通过元数据预过滤减少搜索空间，提高效率

### 2. 仅向量搜索（Vector Only）
- **位置**: 所有Follower节点
- **描述**: 在所有follower节点上执行向量搜索，不使用元数据过滤
- **优势**: 保证不会遗漏任何相关图片，召回率最高

### 3. 仅元数据搜索（Metadata Only）
- **位置**: Leader节点
- **描述**: 仅使用元数据（时间、位置、标签等）进行搜索，不进行向量相似度计算
- **优势**: 速度最快，不需要计算向量相似度

## 使用方法

### 方式一：在命令行交互界面中使用

启动Leader节点后，可以使用以下命令：

```bash
# 1. 查看可用命令
> help

# 2. 单独测试每种搜索方法

# 仅元数据搜索
> search_metadata a photo taken in New York in 2023

# 仅向量搜索（所有follower）
> search_vector a beautiful sunset over the ocean

# MetaFusion搜索（元数据 + 向量）
> search_metafusion a cat sitting on a bench in the park

# 3. 一次性比较所有三种方法
> compare a photo of mountains taken in summer
```

### 方式二：在Python代码中调用

```python
from leader.leader import Leader

# 初始化Leader节点
leader_node = Leader(
    host='localhost',
    port=8000,
    base_dir='state/',
    model_name='ViT-B/32',
    device='cpu',
    normalize=True
)

# 方法1: 单独调用每种搜索方法
prompt = "a beach photo taken in California"

# 仅元数据搜索
metadata_results = leader_node.search(
    prompt=prompt,
    search_mode='metadata_only'
)

# 仅向量搜索
leader_node.search(
    prompt=prompt,
    vector_search=True,
    search_mode='vector_only'
)

# MetaFusion搜索
leader_node.search(
    prompt=prompt,
    vector_search=True,
    search_mode='metafusion'
)

# 方法2: 使用比较函数一次性测试所有方法
results = leader_node.compare_search_methods(
    prompt=prompt,
    wait_time=5  # 等待向量搜索完成的时间（秒）
)

# 分析结果
print(f"元数据搜索结果数: {results['metadata_only']['count']}")
print(f"向量搜索结果数: {results['vector_only']['count']}")
print(f"MetaFusion结果数: {results['metafusion']['count']}")
```

## 比较指标

### 1. 性能指标
- **搜索耗时**: 每种方法完成搜索的时间
- **结果数量**: 返回的图片数量

### 2. 准确度指标
- **召回率（Recall）**: 在所有相关图片中找到的比例
  - 向量搜索 = 基准（最高召回率）
  - MetaFusion召回率 = MetaFusion结果 / 向量搜索结果
  
- **搜索空间减少率**: MetaFusion相比向量搜索减少的搜索范围
  - 减少率 = (1 - MetaFusion搜索的silos数 / 总silos数) × 100%

### 3. 效率指标
- **搜索的Silo数量**: 实际查询的follower节点数
- **平均每个Silo的响应时间**

## 输出示例

```
================================================================================
开始搜索方法对比测试
查询提示词: 'a photo of mountains taken in summer'
================================================================================

[测试 1/3] 仅元数据搜索 (Leader节点)...
完成时间: 0.032秒, 结果数量: 45

[测试 2/3] 仅向量搜索 (所有Follower节点)...
等待 5 秒收集结果...
完成时间: 5.234秒, 结果数量: 128

[测试 3/3] MetaFusion搜索 (元数据过滤 + 向量搜索)...
等待 5 秒收集结果...
完成时间: 5.156秒, 结果数量: 87

================================================================================
搜索方法对比总结
================================================================================
查询提示词: 'a photo of mountains taken in summer'

【性能对比】
方法                   耗时(秒)          结果数量
--------------------------------------------------
仅元数据搜索           0.032           45
仅向量搜索             5.234           128
MetaFusion            5.156           87

【结果对比】
MetaFusion vs 仅向量搜索: 搜索空间减少了 32.0%

【Top-5 结果预览】

仅元数据搜索:
  1. photo_id=abc123, silo_id=2
  2. photo_id=def456, silo_id=2
  3. photo_id=ghi789, silo_id=3
  4. photo_id=jkl012, silo_id=1
  5. photo_id=mno345, silo_id=2

仅向量搜索:
  1. photo_id=xyz789, score=0.9234
  2. photo_id=abc123, score=0.9102
  3. photo_id=def456, score=0.8876
  4. photo_id=uvw234, score=0.8654
  5. photo_id=rst567, score=0.8432

MetaFusion:
  1. photo_id=abc123, score=0.9102
  2. photo_id=def456, score=0.8876
  3. photo_id=ghi789, score=0.8543
  4. photo_id=jkl012, score=0.8321
  5. photo_id=mno345, score=0.8198

================================================================================
```

## 注意事项

1. **等待时间设置**: 向量搜索是异步的，需要设置合适的`wait_time`来确保收集到所有follower的结果。建议：
   - 少量数据（<1000张）：3-5秒
   - 中等数据（1000-10000张）：5-10秒
   - 大量数据（>10000张）：10-15秒

2. **Follower节点状态**: 确保所有follower节点都是alive状态，使用`ls`命令查看

3. **元数据质量**: 仅元数据搜索的效果取决于图片的元数据质量（EXIF信息等）

4. **提示词要求**: 比较测试时，提示词最好包含时间、地点等元数据信息，例如：
   - ✅ "a beach photo taken in California in summer 2023"
   - ❌ "a cat" (缺少元数据信息，MetaFusion无法发挥优势)

## 实验建议

### 实验1: 性能对比
测试不同数据规模下三种方法的性能差异

### 实验2: 准确度对比
使用包含丰富元数据的查询，对比召回率和精确度

### 实验3: 搜索空间减少效果
分析MetaFusion在不同查询下的搜索空间减少率

### 实验4: 边界情况测试
- 无元数据的图片查询
- 非常宽泛的时间范围
- 极其具体的位置信息

