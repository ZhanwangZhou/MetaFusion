# 快速开始：搜索方法对比测试

## 5分钟快速上手

### 步骤1: 启动系统

```bash
# 终端1: 启动Leader节点
python main.py leader

# 终端2: 启动Follower节点
python main.py follower --port 9000

# 终端3 (可选): 启动更多Follower节点
python main.py follower --port 9001
```

### 步骤2: 上传测试数据

在Leader终端中执行：
```
> mass_upload path/to/your/photos
```

### 步骤3: 运行对比测试

#### 方法A: 使用命令行（推荐初学者）

在Leader终端中执行：
```
> compare a photo taken in summer 2023
```

#### 方法B: 使用测试脚本（推荐批量测试）

新开一个终端：
```bash
python test_search_comparison.py
# 选择选项 1（完整对比测试）
```

#### 方法C: 单独测试每种方法

```
> search_metadata a photo in New York
> search_vector a beautiful sunset
> search_metafusion a beach photo in California
```

## 可用命令速查

| 命令 | 功能 | 示例 |
|------|------|------|
| `ls` | 查看节点状态 | `ls` |
| `upload <path>` | 上传单张图片 | `upload test.jpg` |
| `mass_upload <dir>` | 批量上传 | `mass_upload ./photos` |
| `search_metadata <prompt>` | 仅元数据搜索 | `search_metadata photo in 2023` |
| `search_vector <prompt>` | 仅向量搜索 | `search_vector sunset` |
| `search_metafusion <prompt>` | MetaFusion搜索 | `search_metafusion beach` |
| `compare <prompt>` | 对比所有方法 | `compare cat photo` |
| `help` | 查看帮助 | `help` |

## 输出解读

### 比较报告包含：

1. **性能对比** - 各方法的耗时
2. **结果数量** - 返回的图片数量
3. **搜索空间减少率** - MetaFusion相比全量搜索的优化程度
4. **Top-5预览** - 最相关的5张图片

### 示例输出：

```
【性能对比】
方法                   耗时(秒)          结果数量
--------------------------------------------------
仅元数据搜索           0.032           45
仅向量搜索             5.234           128
MetaFusion            5.156           87

【结果对比】
MetaFusion vs 仅向量搜索: 搜索空间减少了 32.0%
```

**解读**：
- ✅ MetaFusion通过元数据过滤，将搜索空间减少了32%
- ✅ 耗时几乎没有增加（5.156秒 vs 5.234秒）
- ✅ 在保持高召回率的同时提升了效率

## 测试提示

### 好的测试查询（能体现MetaFusion优势）：
✅ "a photo taken in New York in summer 2023"  
✅ "sunset over the beach in California"  
✅ "mountain landscape in winter"  

### 不太适合的查询：
❌ "a cat"（没有元数据信息）  
❌ "red color"（过于模糊）  

## 常见问题

**Q: 为什么向量搜索需要等待几秒？**  
A: 向量搜索是异步的，需要等待所有follower返回结果。可以通过`wait_time`参数调整等待时间。

**Q: 为什么元数据搜索没有返回结果？**  
A: 可能是图片缺少EXIF元数据，或查询条件太严格。

**Q: 如何提高测试准确性？**  
A: 使用包含丰富元数据（时间、GPS等）的图片，并在查询中包含相应的元数据信息。

**Q: 可以同时运行多个查询吗？**  
A: 可以，但建议等待前一个查询完成后再执行下一个，以避免结果混淆。

## 下一步

1. 📖 阅读详细文档: `SEARCH_COMPARISON_GUIDE.md`
2. 🔧 查看技术细节: `SEARCH_COMPARISON_UPDATE.md`
3. 🧪 进行更多实验: 尝试不同的查询和数据集

## 需要帮助？

如果遇到问题：
1. 检查所有节点是否正常运行（使用`ls`命令）
2. 确认数据库连接正常
3. 验证图片是否成功上传
4. 查看日志文件了解详细错误信息

---
祝测试顺利！🚀

