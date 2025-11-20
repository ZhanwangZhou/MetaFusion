# 搜索方法对比功能更新说明

## 更新概述

本次更新为MetaFusion系统添加了三种搜索方法的对比测试功能，用于评估和比较不同搜索策略的性能和准确度。

## 更新内容

### 1. 修改的文件

#### `leader/leader.py`
- **修改的函数**: `search()`
  - 添加了 `search_mode` 参数，支持三种搜索模式：
    - `'metafusion'`: 元数据过滤 + 向量搜索（默认）
    - `'vector_only'`: 仅向量搜索（所有follower节点）
    - `'metadata_only'`: 仅元数据搜索（leader节点）
  
- **新增函数**: `compare_search_methods()`
  - 自动执行三种搜索方法并生成对比报告
  - 提供性能指标、结果数量和搜索效率分析
  
- **新增函数**: `_print_comparison_summary()`
  - 格式化输出对比测试的详细结果
  - 包含性能对比、结果对比和Top-K结果预览

- **修改的函数**: `_handle_search_result()`
  - 增强了结果显示格式
  - 添加了搜索模式标识
  - 改进了结果排序和展示

#### `main.py`
- **新增命令**:
  - `search_metadata <prompt>` - 仅元数据搜索
  - `search_vector <prompt>` - 仅向量搜索
  - `search_metafusion <prompt>` - MetaFusion搜索
  - `compare <prompt>` - 一次性对比所有三种方法
  - `help` - 显示所有可用命令

### 2. 新增的文件

#### `SEARCH_COMPARISON_GUIDE.md`
详细的使用指南，包含：
- 三种搜索方法的说明
- 使用方法和示例
- 评估指标说明
- 实验建议

#### `test_search_comparison.py`
独立的测试脚本，提供：
- 完整的对比测试流程
- 单独测试各方法的选项
- 统计报告生成
- 易用的交互界面

## 使用方式

### 方式1: 命令行界面

```bash
# 启动Leader节点
python main.py leader

# 在交互界面中使用新命令
> help                              # 查看所有命令
> search_metadata a photo in 2023   # 测试元数据搜索
> search_vector a beautiful sunset  # 测试向量搜索
> compare a beach photo             # 对比所有方法
```

### 方式2: 独立测试脚本

```bash
python test_search_comparison.py
```

### 方式3: Python代码调用

```python
from leader.leader import Leader

leader = Leader('localhost', 8000, 'state/', 'ViT-B/32', 'cpu', True)

# 方法1: 单独测试
results = leader.search(prompt="a photo in 2023", search_mode='metadata_only')

# 方法2: 对比测试
results = leader.compare_search_methods(prompt="a beach photo")
```

## 三种搜索方法对比

| 方法 | 位置 | 优势 | 适用场景 |
|------|------|------|----------|
| **Metadata Only** | Leader节点 | 速度最快 | 有明确时空信息的查询 |
| **Vector Only** | 所有Follower | 召回率最高 | 需要完整搜索空间 |
| **MetaFusion** | Leader + 部分Follower | 平衡效率和准确度 | 大多数实际应用 |

## 评估指标

1. **性能指标**
   - 搜索耗时
   - 结果数量

2. **效率指标**
   - 搜索空间减少率
   - 查询的Silo数量

3. **准确度指标**
   - 召回率（相对于Vector Only）
   - Top-K结果质量

## 示例输出

```
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
```

## 注意事项

1. **向量搜索是异步的**：需要设置合适的等待时间（`wait_time`参数）
2. **Follower状态**：确保follower节点状态为'alive'
3. **元数据质量**：元数据搜索的效果依赖于图片的EXIF信息质量
4. **提示词设计**：包含时间、地点信息的提示词更能体现MetaFusion的优势

## 向后兼容性

所有更改都保持向后兼容：
- 原有的 `search()` 函数调用方式仍然有效
- 默认行为是MetaFusion搜索
- `vector_search` 参数仍然支持

## 建议的实验流程

1. **准备数据**：上传包含元数据的测试图片
2. **检查状态**：使用 `ls` 命令确认follower状态
3. **单独测试**：先分别测试三种方法理解其特点
4. **对比测试**：使用 `compare` 命令进行全面对比
5. **分析结果**：根据输出报告评估各方法的性能

## 技术细节

### 搜索流程

**Metadata Only**:
```
Query → Extract Metadata → Filter Silos → Query Database → Return Results
```

**Vector Only**:
```
Query → Send to All Followers → Vector Search → Collect Results → Return
```

**MetaFusion**:
```
Query → Extract Metadata → Filter Silos → Send to Selected Followers 
      → Vector Search → Collect Results → Return
```

### 代码改动摘要

- `leader.py`: +130行新增代码
- `main.py`: +20行新增代码
- 新增文档和测试脚本

## 未来扩展

可能的改进方向：
1. 添加准确度评估（需要标注数据）
2. 支持批量测试和自动化评估
3. 可视化对比结果
4. 性能profiling和优化建议
5. A/B测试框架

## 问题反馈

如果遇到问题，请检查：
1. Leader和Follower节点是否正常运行
2. 数据库连接是否正常
3. 图片是否包含元数据信息
4. wait_time是否设置合理

---

更新日期: 2025-11-20
版本: MetaFusion v1.1

