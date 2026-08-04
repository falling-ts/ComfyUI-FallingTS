---
path: seedance/**
---

## Doubao Seedance 2.0 系列教程

Doubao Seedance 2.0 系列（下文简称 Seedance 2.0 系列）模型支持图像、视频、音频、文本等多种模态内容输入，具备视频生成、视频编辑、视频延长等能力，可高精度还原物品细节、音色、效果、风格、运镜等，保持稳定角色特征，赋予使用者如同导演般的掌控权。本文介绍 Seedance 2.0 系列模型的专属能力，帮助您快速实现 [Video Generation API](https://www.volcengine.com/docs/82379/1520758) 调用。

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">开通 Seedance 2.0 系列模型前，请确保您满足以下任一条件：</div>



* <div data-tips="true" data-tips-type="tip">账户余额 \> 200 元（<a href="https://console.volcengine.com/finance/fund/recharge">前往充值</a>）</div>


* <div data-tips="true" data-tips-type="tip">已购买 Seedance 2.0 系列资源包且有可用余量 （<a href="https://console.volcengine.com/common-buy/fast/ark_bd%7C%7Cd682ppeeq1mp7kd5q0e0">前往购买</a>）</div>



<div data-tips="true" data-tips-type="tip">详细规则见 <a href="https://www.volcengine.com/docs/82379/2191775">Seedance 2.0 系列模型资源包使用规则</a>。</div>


<span id="e000144b"></span>
# 新手入门

本入门教程专为 **API 新手用户** 设计，帮助您一键搭建 Python 开发环境、完成虚拟环境创建和方舟 SDK 安装，并提供直接可运行的 Seedance 2.0 系列调用代码，您只需修改对应的输入素材，即可开始您的视频生成创作。

**1. 准备工作**

在开始之前，请确保您已经完成以下准备：


1. **注册账号** ：确保您拥有火山引擎账号并已[登录](https://console.volcengine.com/)。

2. **获取 API Key** ：访问 [API Key 管理页面](https://console.volcengine.com/ark/region:ark+cn-beijing/apikey)，点击 **创建 API Key** ，并复制保存您的 API Key。注意请妥善保管您的 API Key，不要泄露给他人。

3. [开通模型](https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=model&projectName=default&tab=ComputerVision)[ ](https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=model&projectName=default&tab=ComputerVision)：请确保您的账户余额大于等于 200 元，或已[购买资源包](https://console.volcengine.com/common-buy/fast/ark_bd%7C%7Cd682ppeeq1mp7kd5q0e0)，否则无法开通 Seedance 2.0 系列模型。

4. **下载并解压文件** ：点击下载下方附件，将其解压到您的本地目录（如桌面或“下载”文件夹）。

   <Attachment link="https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/1c5fc49ecf2d40b89ef7dd12765e23e7~tplv-goo7wpa0wc-image.image" name="ark_seedance2.0_quickstart_package.zip">ark_seedance2.0_quickstart_package.zip</Attachment>
   


**2.操作步骤**


<Tabs>
<Tab zoneid="LranLCMUDi" title="Windows 用户">
<TabTitle>Windows 用户</TabTitle>

1. 进入 `scripts/init_dev_env` 目录。

2. 双击运行 `setup_windows.bat`。

3. 脚本会自动执行以下操作：

   * 下载 uv 工具。

   * 自动下载 Python 3.12（如果不干扰您的系统 Python）。

   * 创建虚拟环境 .`venv`。

   * 安装方舟 SDK。

4. 完成后，在项目根目录会生成一个 `run_demo.bat`。

5. 双击 `run_demo.bat`，即可运行 Python SDK 示例代码(python/demo_standard.py)。


</Tab>
<Tab zoneid="RjPbkqOJnM" title="macOS 用户">
<TabTitle>macOS 用户</TabTitle>

1. 打开终端，进入 `scripts/init_dev_env` 目录。

2. 运行构建脚本：


```Plain
./setup_mac.sh
```



3. 脚本会自动配置好所有环境。

4. 完成后，在项目根目录会生成一个 `run_demo.sh`。

5. 运行 `./run_demo.sh` 即可运行 Python SDK 示例代码(python/demo_standard.py)。


</Tab>
</Tabs>


**3.运行说明**

运行脚本后，您将看到如下流程：


1. **API Key 校验** ：脚本会自动检测您本地是否配置了`ARK_API_KEY`环境变量。如果没有，会提示您手动输入。

2. **素材预览** ：脚本会自动在您的默认浏览器中弹出一个本地生成的 HTML 页面，直观地展示本次任务的文本提示词、待替换的参考图片以及原始参考视频。

3. **任务创建与轮询** ：脚本向火山方舟服务器发起异步请求。由于视频生成需要一定时间，控制台会每隔 30 秒打印一次任务状态（如 `running`等）。

4. **获取结果** ：任务成功后，控制台会输出一段最终生成的视频 URL。您可以复制该链接到浏览器下载或在线播放。


**4.下一步**

在成功跑通本示例后，您可以尝试修改 `python/``demo_standard.py`，来打造您专属的视频生成任务：


1. 修改文本提示词


找到代码中的 `user_content` 变量，更改为您想要的画面描述。

2. 替换输入素材 (图片、视频、音频)

您可以将 `reference_image_url`、`reference_video_url` 和 `reference_audio_url` 替换为您自己的素材链接。

**注意** ：请确保 URL 是公网可公开访问的链接（建议存放在 TOS 对象存储服务中，并配置为公共读）。

3. 继续学习下文中丰富的使用示例。

<span id="fd30cc1a"></span>
# 模型能力

Seedance 2.0 系列模型目前包括 Doubao Seedance 2.0（下文简称 Seedance 2.0）、Doubao Seedance 2.0 Fast（下文简称 Seedance 2.0 Fast）和 Doubao Seedance 2.0 Mini（下文简称 Seedance 2.0 Mini）。三者支持的功能基本一致，主要区别在于生成品质与成本的取舍：


* 追求最高生成品质，推荐使用 Seedance 2.0；

* 兼顾成本与生成速度，不要求极致品质，推荐使用 Seedance 2.0 Fast；

* 追求更低成本，推荐使用 Seedance 2.0 Mini。



<span aceTableMode="list" aceTableWidth="3,3,3,3,3"></span>
|模型名称 | |[Seedance 2.0](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0&projectName=default) |[Seedance 2.0 Fast](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0-fast&projectName=default) |[Seedance 2.0 Mini](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0-mini&projectName=default) |
|---|---|---|---|---|
|Model ID | |doubao\-seedance\-2\-0\-260128 |doubao\-seedance\-2\-0\-fast\-260128 |doubao\-seedance\-2\-0\-mini\-260615 |
|[文生视频](https://www.volcengine.com/docs/82379/2298881#4e74bcee) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[图生视频-首帧](https://www.volcengine.com/docs/82379/2298881#979b2d28) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[图生视频-首尾帧](https://www.volcengine.com/docs/82379/2298881#0d55ca07) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[多模态参考](https://www.volcengine.com/docs/82379/2291680#50e1b4ea)【New】 |图片参考 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
||视频参考 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
||组合参考<br><br><br>* 图片 + 音频<br><br>* 图片 + 视频<br><br>* 视频 + 音频<br><br>* 图片 + 视频 + 音频 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[编辑视频](https://www.volcengine.com/docs/82379/2291680#75a28782)【New】 | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[延长视频](https://www.volcengine.com/docs/82379/2291680#46d77653)【New】 | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[生成有声视频](https://www.volcengine.com/docs/82379/2298881#979b2d28)<br><br>> "generate_audio": "true" | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[联网搜索工具](https://www.volcengine.com/docs/82379/2291680#c40ed3ef)【New】 | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[样片模式](https://www.volcengine.com/docs/82379/2298881#5acd28c8) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[返回视频产物对应的尾帧图](https://www.volcengine.com/docs/82379/2298881#141cf7fa)<br><br>> "return_last_frame":<br><br>> "true" | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[输出视频规格](https://www.volcengine.com/docs/82379/2298881#9fe4cce0) |输出分辨率<br><br>> "resolution": "720p" |480p, 720p, 1080p, 4k（10bit 位深） |480p, 720p |480p, 720p |
| |输出宽高比<br><br>> "ratio":"16:9" |21:9, 16:9, 4:3,<br><br>1:1, 3:4, 9:16 |21:9, 16:9, 4:3,<br><br>1:1, 3:4, 9:16 |21:9, 16:9, 4:3,<br><br>1:1, 3:4, 9:16 |
| |输出时长<br><br>> "duration": 5 |4~15 秒 |4~15 秒 |4~15 秒 |
| |输出视频格式 |mp4 |mp4 |mp4 |
|[离线推理](https://www.volcengine.com/docs/82379/2298881#c3588bd1)<br><br>> "service_tier": "flex" | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|在线推理限流 |最大 RPM |非 4k 分辨率：<br><br><br>* 企业用户：600<br><br>* 个人用户：180<br><br><br>4k 分辨率：<br><br><br>* 企业用户：15<br><br>* 个人用户：15 |* 企业用户：600<br><br>* 个人用户：180 |* 企业用户：600<br><br>* 个人用户：180 |
| |最大并发数 |非 4k 分辨率：<br><br><br>* 企业用户：10<br><br>* 个人用户：3<br><br><br>4k 分辨率：<br><br><br>* 企业用户：1<br><br>* 个人用户：1 |* 企业用户：10<br><br>* 个人用户：3 |* 企业用户：10<br><br>* 个人用户：3 |
|离线推理限流 |TPD |\- |\- |\- |


<span id="dcb767c3"></span>
# 基础使用

<span id="50e1b4ea"></span>
## 多模态参考

输入文本、参考图、视频（可带音轨）和音频等内容，来生成一段新视频。可继承参考图片的角色形象、视觉风格、画面构图；参考视频的主体内容、运镜方式、动作表现、整体风格；以及参考音频的音色、音乐旋律、对话内容等核心信息。

效果预览如下（访问[模型卡片](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0)查看更多示例）：


<span aceTableMode="list" aceTableWidth="4,5,5"></span>
|输入：文本 |输入：图片、视频、音频 |输出 |
|---|---|---|
|全程使用 **视频1** 的第一视角构图，全程使用 **音频1** 作为背景音乐。第一人称视角果茶宣传广告，seedance牌「苹苹安安」苹果果茶限定款；首帧为 **图片1** ，你的手摘下一颗带晨露的阿克苏红苹果，轻脆的苹果碰撞声；2\-4 秒：快速切镜，你的手将苹果块投入雪克杯，加入冰块与茶底，用力摇晃，冰块碰撞声与摇晃声卡点轻快鼓点，背景音：「鲜切现摇」；4\-6 秒：第一人称成品特写，分层果茶倒入透明杯，你的手轻挤奶盖在顶部铺展，在杯身贴上粉红包标，镜头拉近看奶盖与果茶的分层纹理；6\-8 秒：第一人称手持举杯，你将 **图片2** 中的果茶举到镜头前（模拟递到观众面前的视角），杯身标签清晰可见，背景音「来一口鲜爽」，尾帧定格为 **图片2** 。背景声音统一为女生音色。 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/0ba05cd435f543c5bc65c378d94d094a" controls></video><br><br><br><span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/37ef4b6af8944a6d9b54ef1c541c1b0e~tplv-goo7wpa0wc-image.image) </span> <span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/7b904d6b46d24f059de7697620058b7f~tplv-goo7wpa0wc-image.image) </span><br><br><Attachment link="https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/8bbbacecfd7d48dfa7ec6ec74125eb04~tplv-goo7wpa0wc-image.image" name="r2v_tea_audio1.mp3">r2v_tea_audio1.mp3</Attachment><br> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/dab46ce2289a4a8ead76711bb02f2e1d" controls></video><br> |



<Tabs>
<Tab zoneid="MVg5tULYw7" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID 
        content=[
            {
                "type": "text",
                "text": "全程使用视频1的第一视角构图，全程使用音频1作为背景音乐。第一人称视角果茶宣传广告，seedance牌「苹苹安安」苹果果茶限定款；首帧为图片1，你的手摘下一颗带晨露的阿克苏红苹果，轻脆的苹果碰撞声；2-4 秒：快速切镜，你的手将苹果块投入雪克杯，加入冰块与茶底，用力摇晃，冰块碰撞声与摇晃声卡点轻快鼓点，背景音：「鲜切现摇」；4-6 秒：第一人称成品特写，分层果茶倒入透明杯，你的手轻挤奶盖在顶部铺展，在杯身贴上粉红包标，镜头拉近看奶盖与果茶的分层纹理；6-8 秒：第一人称手持举杯，你将图片2中的果茶举到镜头前（模拟递到观众面前的视角），杯身标签清晰可见，背景音「来一口鲜爽」，尾帧定格为图片2。背景声音统一为女生音色。",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic1.jpg"
                },
                "role": "reference_image",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic2.jpg"
                },
                "role": "reference_image",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_tea_video1.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "audio_url",
                "audio_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_audio/r2v_tea_audio1.mp3"
                },
                "role": "reference_audio",
            },
        ],
        generate_audio=True,
        ratio="16:9",
        duration=11,
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
```



</Tab>
<Tab zoneid="oIeV9gG7nX" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
           
    public static void main(String[] args) {
        
        // Model ID
        final String modelId = "doubao-seedance-2-0-260128";
        // Text prompt
        final String prompt = "全程使用视频1的第一视角构图，全程使用音频1作为背景音乐。第一人称视角果茶宣传广告，seedance牌「苹苹安安」苹果果茶限定款；" +
                "首帧为图片1，你的手摘下一颗带晨露的阿克苏红苹果，轻脆的苹果碰撞声；" +
                "2-4 秒：快速切镜，你的手将苹果块投入雪克杯，加入冰块与茶底，用力摇晃，冰块碰撞声与摇晃声卡点轻快鼓点，背景音：「鲜切现摇」；" +
                "4-6 秒：第一人称成品特写，分层果茶倒入透明杯，你的手轻挤奶盖在顶部铺展，在杯身贴上粉红包标，镜头拉近看奶盖与果茶的分层纹理；" +
                "6-8 秒：第一人称手持举杯，你将图片2中的果茶举到镜头前（模拟递到观众面前的视角），杯身标签清晰可见，背景音「来一口鲜爽」，尾帧定格为图片2。" +
                "背景声音统一为女生音色。";
        
        // Example resource URLs
        final String refImage1 = "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic1.jpg";
        final String refImage2 = "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic2.jpg";
        final String refVideo = "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_tea_video1.mp4";
        final String refAudio = "https://ark-project.tos-cn-beijing.volces.com/doc_audio/r2v_tea_audio1.mp3";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "16:9";      
        final long videoDuration = 11L;          
        final boolean showWatermark = true;

        System.out.println("----- create request -----");
        // Build request content
        List<Content> contents = new ArrayList<>();
        
        // 1. Text prompt
        contents.add(Content.builder()
                .type("text")
                .text(prompt)
                .build());
                
        // 2. Reference image 1
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url(refImage1)
                        .build())
                .role("reference_image")
                .build());

        // 3. Reference image 2
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url(refImage2)
                        .build())
                .role("reference_image")
                .build());

        // 4. Reference video
        contents.add(Content.builder()
                .type("video_url")
                .videoUrl(CreateContentGenerationTaskRequest.VideoUrl.builder()
                        .url(refVideo)  
                        .build())
                .role("reference_video")
                .build());

        // 5. Reference audio
        contents.add(Content.builder()
                .type("audio_url")
                .audioUrl(CreateContentGenerationTaskRequest.AudioUrl.builder()
                        .url(refAudio)
                        .build())
                .role("reference_audio")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(showWatermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        System.out.println("----- polling task status -----");
        try {
            while (true) {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    if (getResponse.getError() != null) {
                        System.out.println("Error: " + getResponse.getError().getMessage());
                    }
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            System.err.println("Polling interrupted");
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
        } finally {
            service.shutdownExecutor();
        }
    }
}
```



</Tab>
<Tab zoneid="NFtJ40Cdve" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Initialize Ark client
    client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()

    // Model ID
    modelID := "doubao-seedance-2-0-260128"
    // Text prompt
    prompt := "全程使用视频1的第一视角构图，全程使用音频1作为背景音乐。第一人称视角果茶宣传广告，seedance牌「苹苹安安」苹果果茶限定款；" +
        "首帧为图片1，你的手摘下一颗带晨露的阿克苏红苹果，轻脆的苹果碰撞声；" +
        "2-4 秒：快速切镜，你的手将苹果块投入雪克杯，加入冰块与茶底，用力摇晃，冰块碰撞声与摇晃声卡点轻快鼓点，背景音：「鲜切现摇」；" +
        "4-6 秒：第一人称成品特写，分层果茶倒入透明杯，你的手轻挤奶盖在顶部铺展，在杯身贴上粉红包标，镜头拉近看奶盖与果茶的分层纹理；" +
        "6-8 秒：第一人称手持举杯，你将图片2中的果茶举到镜头前（模拟递到观众面前的视角），杯身标签清晰可见，背景音「来一口鲜爽」，尾帧定格为图片2。" +
        "背景声音统一为女生音色。"

    // Example resource URLs
    refImage1 := "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic1.jpg"
    refImage2 := "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic2.jpg"
    refVideo := "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_tea_video1.mp4"
    refAudio := "https://ark-project.tos-cn-beijing.volces.com/doc_audio/r2v_tea_audio1.mp3"

    // Output video parameters
    generateAudio := true
    videoRatio := "16:9"
    videoDuration := int64(11)
    showWatermark := true

    // 1. Create video generation task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model:         modelID,
        GenerateAudio: volcengine.Bool(generateAudio),
        Ratio:         volcengine.String(videoRatio),
        Duration:      volcengine.Int64(videoDuration),
        Watermark:     volcengine.Bool(showWatermark),
        Content: []*model.CreateContentGenerationContentItem{
            {
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String(prompt),
            },
            {
                Type: model.ContentGenerationContentItemType("image_url"),
                ImageURL: &model.ImageURL{
                    URL: refImage1,
                },
                Role: volcengine.String("reference_image"),
            },
            {
                Type: model.ContentGenerationContentItemType("image_url"),
                ImageURL: &model.ImageURL{
                    URL: refImage2,
                },
                Role: volcengine.String("reference_image"),
            },
            {
                Type: model.ContentGenerationContentItemType("video_url"),
                VideoURL: &model.VideoUrl{
                    Url: refVideo,
                },
                Role: volcengine.String("reference_video"),
            },
            {
                Type: model.ContentGenerationContentItemType("audio_url"),
                AudioURL: &model.AudioUrl{
                    Url: refAudio,
                },
                Role: volcengine.String("reference_audio"),
            },
        },
    }

    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v\n", err)
        return
    }

    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s\n", taskID)

    // 2. Poll task status
    pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v\n", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s\n", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip">您可任意组合以下模态内容，注意不支持“文本+音频”、“纯音频” 输入。</div>


   * <div data-tips="true" data-tips-type="tip">文本</div>


   * <div data-tips="true" data-tips-type="tip">图片：0~9 张</div>


   * <div data-tips="true" data-tips-type="tip">视频：0~3 个</div>


   * <div data-tips="true" data-tips-type="tip">音频：0~3 个</div>


* <div data-tips="true" data-tips-type="tip"><strong>进阶用法</strong> ：多模态生视频可通过提示词指定参考图片作为首帧/尾帧，间接实现“首尾帧+多模态参考”效果。若需严格保障首尾帧和指定图片一致， <strong>优先使用图生视频\-首尾帧</strong> （配置 role 为 first_frame/last_frame）。</div>


* <div data-tips="true" data-tips-type="tip">各个模态信息输入要求参见<a href="https://www.volcengine.com/docs/82379/1366799#63a97f09">多模态输入</a>。</div>



<span id="75a28782"></span>
## 编辑视频

您可以提供待编辑的视频、参考图片或音频，并结合使用提示词，完成多种视频编辑任务，例如：替换视频主体、视频中对象增删改、局部画面重绘/修复等。

效果预览如下（访问[模型卡片](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0)查看更多示例）：


<span aceTableMode="list" aceTableWidth="4,5,5"></span>
|输入：文本 |输入：视频&图片 |输出 |
|---|---|---|
|将 **视频1** 礼盒中的香水替换成 **图像1** 中的面霜，运镜不变 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/0a1afd3250d84b8995e9c0aa61b57d38" controls></video><br><br><br><span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/791b783fc6cd4394b13f41b66b5ff461~tplv-goo7wpa0wc-image.image) </span> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/fd7bcf4eaf504f50aeeebd48ce35c06a" controls></video><br> |



<Tabs>
<Tab zoneid="njaBTMOhlJ" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID 
        content=[
            {
                "type": "text",
                "text": "将视频1礼盒中的香水替换成图片1中的面霜，运镜不变",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_edit_pic1.jpg"
                },
                "role": "reference_image",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_edit_video1.mp4"
                },
                "role": "reference_video",
            },
        ],
        generate_audio=True,
        ratio="16:9",
        duration=5,
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
```



</Tab>
<Tab zoneid="olsP2m84xA" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
           
    public static void main(String[] args) {
        
        // Model ID
        final String modelId = "doubao-seedance-2-0-260128"; 
        // Text prompt
        final String prompt = "将视频1礼盒中的香水替换成图片1中的面霜，运镜不变";
        
        // Example resource URLs
        final String refImage1 = "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_edit_pic1.jpg";
        final String refVideo = "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_edit_video1.mp4";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "16:9";      
        final long videoDuration = 5L;          
        final boolean showWatermark = true;

        System.out.println("----- create request -----");
        // Build request content
        List<Content> contents = new ArrayList<>();
        
        // 1. Text prompt
        contents.add(Content.builder()
                .type("text")
                .text(prompt)
                .build());
                
        // 2. Reference image 1
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url(refImage1)
                        .build())
                .role("reference_image")
                .build());

        // 3. Reference video
        contents.add(Content.builder()
                .type("video_url")
                .videoUrl(CreateContentGenerationTaskRequest.VideoUrl.builder()
                        .url(refVideo)  
                        .build())
                .role("reference_video")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(showWatermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        System.out.println("----- polling task status -----");
        try {
            while (true) {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    if (getResponse.getError() != null) {
                        System.out.println("Error: " + getResponse.getError().getMessage());
                    }
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            System.err.println("Polling interrupted");
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
        } finally {
            service.shutdownExecutor();
        }
    }
}
```



</Tab>
<Tab zoneid="ckhFZAs8VM" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Initialize Ark client
    client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()

    // Model ID
    modelID := "doubao-seedance-2-0-260128"
    // Text prompt
    prompt := "将视频1礼盒中的香水替换成图片1中的面霜，运镜不变"

    // Example resource URLs
    refImage1 := "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_edit_pic1.jpg"
    refVideo1 := "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_edit_video1.mp4"

    // Output video parameters
    generateAudio := true
    videoRatio := "16:9"
    videoDuration := int64(5)
    showWatermark := true

    // 1. Create video generation task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model:         modelID,
        GenerateAudio: volcengine.Bool(generateAudio),
        Ratio:         volcengine.String(videoRatio),
        Duration:      volcengine.Int64(videoDuration),
        Watermark:     volcengine.Bool(showWatermark),
        Content: []*model.CreateContentGenerationContentItem{
            {
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String(prompt),
            },
            {
                Type: model.ContentGenerationContentItemType("image_url"),
                ImageURL: &model.ImageURL{
                    URL: refImage1,
                },
                Role: volcengine.String("reference_image"),
            },
            {
                Type: model.ContentGenerationContentItemType("video_url"),
                VideoURL: &model.VideoUrl{
                    Url: refVideo1,
                },
                Role: volcengine.String("reference_video"),
            },
        },
    }

    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v\n", err)
        return
    }

    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s\n", taskID)

    // 2. Poll task status
    pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v\n", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s\n", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<span id="46d77653"></span>
## 延长视频

在原有视频基础上，向前或者向后延长视频，或多个视频片段（最多 3 个视频片段）串联成一个连贯视频。

效果预览如下（访问[模型卡片](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0)查看更多示例）：


<span aceTableMode="list" aceTableWidth="4,5,5"></span>
|输入：文本 |输入：待延长视频 |输出 |
|---|---|---|
|**视频1** 中的拱形窗户打开，进入美术馆室内，接 **视频2** ，之后镜头进入画内，接 **视频3** |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/54519ff7266d4f1caa12b8cc95e2dd1d" controls></video><br><br><br><video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/b15d56c80c884faa8526beb6ca540b98" controls></video><br><br><br><video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/f5d327311e094361b15dca0a37b14ab4" controls></video><br> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/849b3f86f609495ca09d559aa14c79ed" controls></video><br> |



<Tabs>
<Tab zoneid="QTvvaZt7Xz" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID 
        content=[
            {
                "type": "text",
                "text": "视频1中的拱形窗户打开，进入美术馆室内，接视频2，之后镜头进入画内，接视频3",
                
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video1.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video2.mp4"
                },
                "role": "reference_video",
            },
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video3.mp4"
                },
                "role": "reference_video",
            },
        ],
        generate_audio=True,
        ratio="16:9",
        duration=8,
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
```



</Tab>
<Tab zoneid="qkZcuGApvR" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
           
    public static void main(String[] args) {
        
        // Model ID
        final String modelId = "doubao-seedance-2-0-260128";
        // Text prompt
        final String prompt = "视频1中的拱形窗户打开，进入美术馆室内，接视频2，之后镜头进入画内，接视频3";
        
        // Example resource URLs
        final String refVideo1 = "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video1.mp4";
        final String refVideo2 = "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video2.mp4";
        final String refVideo3 = "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video3.mp4";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "16:9";      
        final long videoDuration = 8L;          
        final boolean showWatermark = true;

        System.out.println("----- create request -----");
        // Build request content
        List<Content> contents = new ArrayList<>();
        
        // 1. Text prompt
        contents.add(Content.builder()
                .type("text")
                .text(prompt)
                .build());
                
        // 2. Reference video 1
        contents.add(Content.builder()
                .type("video_url")
                .videoUrl(CreateContentGenerationTaskRequest.VideoUrl.builder()
                        .url(refVideo1)  
                        .build())
                .role("reference_video")
                .build());

        // 3. Reference video 2
        contents.add(Content.builder()
                .type("video_url")
                .videoUrl(CreateContentGenerationTaskRequest.VideoUrl.builder()
                        .url(refVideo2)  
                        .build())
                .role("reference_video")
                .build());

        // 4. Reference video 3
        contents.add(Content.builder()
                .type("video_url")
                .videoUrl(CreateContentGenerationTaskRequest.VideoUrl.builder()
                        .url(refVideo3)  
                        .build())
                .role("reference_video")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(showWatermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        System.out.println("----- polling task status -----");
        try {
            while (true) {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    if (getResponse.getError() != null) {
                        System.out.println("Error: " + getResponse.getError().getMessage());
                    }
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            System.err.println("Polling interrupted");
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
        } finally {
            service.shutdownExecutor();
        }
    }
}
```



</Tab>
<Tab zoneid="rA2eQNfno7" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Initialize Ark client
    client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()

    // Model ID
    modelID := "doubao-seedance-2-0-260128"
    // Text prompt
    prompt := "视频1中的拱形窗户打开，进入美术馆室内，接视频2，之后镜头进入画内，接视频3"

    // Example resource URLs
    refVideo1 := "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video1.mp4"
    refVideo2 := "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video2.mp4"
    refVideo3 := "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_extend_video3.mp4"

    // Output video parameters
    generateAudio := true
    videoRatio := "16:9"
    videoDuration := int64(8)
    showWatermark := true

    // 1. Create video generation task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model:         modelID,
        GenerateAudio: volcengine.Bool(generateAudio),
        Ratio:         volcengine.String(videoRatio),
        Duration:      volcengine.Int64(videoDuration),
        Watermark:     volcengine.Bool(showWatermark),
        Content: []*model.CreateContentGenerationContentItem{
            {
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String(prompt),
            },
            {
                Type: model.ContentGenerationContentItemType("video_url"),
                VideoURL: &model.VideoUrl{
                    Url: refVideo1,
                },
                Role: volcengine.String("reference_video"),
            },
            {
                Type: model.ContentGenerationContentItemType("video_url"),
                VideoURL: &model.VideoUrl{
                    Url: refVideo2,
                },
                Role: volcengine.String("reference_video"),
            },
            {
                Type: model.ContentGenerationContentItemType("video_url"),
                VideoURL: &model.VideoUrl{
                    Url: refVideo3,
                },
                Role: volcengine.String("reference_video"),
            },
        },
    }

    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v\n", err)
        return
    }

    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s\n", taskID)

    // 2. Poll task status
    pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v\n", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s\n", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip">向前或向后延长 1 段视频，生成的视频一般只包含原视频的尾部画面。但您也可以通过提示词灵活控制，使其包含原视频内容。 例如：向前延长视频1，[延长内容描述...]， <strong>最后接视频1</strong> 。</div>


* <div data-tips="true" data-tips-type="tip">传入 2~3 段视频，补全中间过渡部分，生成的视频会包含原视频内容和新生成的视频内容。</div>



<span id=".6L6T5Ye6LTRrLeinhumikQ=="></span>
## 输出 4k 视频

> 仅 Seedance 2.0 支持


Seedance 2.0 支持输出 4k 视频，并采用 10bit 位深编码，能够完整保留丰富的色彩层次与平滑的渐变过渡，满足专业影视制作与 HDR 视频内容的要求。

<div data-tips="true" data-tips-type="warning" data-tips-is-title="true">注意</div>


<div data-tips="true" data-tips-type="warning">4k 视频采用 H.265 (HEVC) 编码格式输出，部分播放器/浏览器可能无法直接播放，详见 <a href="https://www.volcengine.com/docs/82379/2291680#4k_player">4k 播放器兼容性说明</a>。</div>



<span aceTableMode="list" aceTableWidth="1,1"></span>
|效果预览1 |效果预览2 |
|---|---|
|<video src="https://ark-project.tos-cn-beijing.volces.com/doc_audio/4K%E5%BD%A9%E5%A6%86-%E9%9F%B3%E4%B9%90.mov" controls></video><br> |<video src="https://ark-project.tos-cn-beijing.volces.com/doc_audio/4K%E6%91%A9%E6%89%98-%E9%9F%B3%E4%B9%90.mov" controls></video><br> |


> 注：效果展示视频由 Seedance 2.0 生成的多个分镜拼接而成，非下述示例代码直接生成。



<Tabs>
<Tab zoneid="i3GYl3IHqT" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128",
        content=[
            {
                "type": "text",
                "text": "生成一段15秒的越野摩托竞技广告感短片。参考图片作为中段飞跃高潮的参考。镜头逻辑依次为：1）中景跟拍，车手从远处沿土坡高速逼近跳台；2）超近低机位后轮飞砂特写，轮胎抓地甩出大量泥土和砂石；3）中近景展示骑手控车、手部发力、悬挂压缩与机械震动；4）侧向英雄中景拍车手冲坡腾空飞跃，画面状态接近图一，泥土在逆光中大面积飞散；5）腾空近景帅气细节，突出头盔护目镜、手部控把、轮胎悬空或车身侧面局部；6）中景跟拍落地，悬挂压缩回弹，随后继续沿土坡赛道高速冲刺收尾。全片同一名骑手、同一辆车、同一条赛道，镜头景别和角度区分清楚，不重复，动作连贯,画面有真实越野跟拍抖动感、速度感、扬土感和夕阳逆光竞技氛围。",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_4k.png"
                },
                "role": "reference_image",
            },
        ],
        generate_audio=True,
        resolution="4k",
        ratio="adaptive",
        duration=15,
        watermark=True,
    )
    print(create_result)


    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
```



</Tab>
<Tab zoneid="zdpjnyG3qi" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
           
    public static void main(String[] args) {
        
        // Model ID
        final String modelId = "doubao-seedance-2-0-260128";
        // Text prompt
        final String prompt = "生成一段15秒的越野摩托竞技广告感短片。参考图片作为中段飞跃高潮的参考。" +
                "镜头逻辑依次为：1）中景跟拍，车手从远处沿土坡高速逼近跳台；" +
                "2）超近低机位后轮飞砂特写，轮胎抓地甩出大量泥土和砂石；" +
                "3）中近景展示骑手控车、手部发力、悬挂压缩与机械震动；" +
                "4）侧向英雄中景拍车手冲坡腾空飞跃，画面状态接近图一，泥土在逆光中大面积飞散；" +
                "5）腾空近景帅气细节，突出头盔护目镜、手部控把、轮胎悬空或车身侧面局部；" +
                "6）中景跟拍落地，悬挂压缩回弹，随后继续沿土坡赛道高速冲刺收尾。" +
                "全片同一名骑手、同一辆车、同一条赛道，镜头景别和角度区分清楚，不重复，动作连贯,画面有真实越野跟拍抖动感、速度感、扬土感和夕阳逆光竞技氛围。";
        
        // Example resource URLs
        final String refImage = "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_4k.png";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoResolution = "4k";
        final String videoRatio = "adaptive";
        final long videoDuration = 15L;
        final boolean showWatermark = true;

        System.out.println("----- create request -----");
        // Build request content
        List<Content> contents = new ArrayList<>();
        
        // 1. Text prompt
        contents.add(Content.builder()
                .type("text")
                .text(prompt)
                .build());
                
        // 2. Reference image
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url(refImage)
                        .build())
                .role("reference_image")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .resolution(videoResolution)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(showWatermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        System.out.println("----- polling task status -----");
        try {
            while (true) {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    if (getResponse.getError() != null) {
                        System.out.println("Error: " + getResponse.getError().getMessage());
                    }
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            System.err.println("Polling interrupted");
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
        } finally {
            service.shutdownExecutor();
        }
    }
}
```



</Tab>
<Tab zoneid="aUq7j6FJpb" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Initialize Ark client
    client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()

    // Model ID
    modelID := "doubao-seedance-2-0-260128"
    // Text prompt
    prompt := "生成一段15秒的越野摩托竞技广告感短片。参考图片作为中段飞跃高潮的参考。" +
        "镜头逻辑依次为：1）中景跟拍，车手从远处沿土坡高速逼近跳台；" +
        "2）超近低机位后轮飞砂特写，轮胎抓地甩出大量泥土和砂石；" +
        "3）中近景展示骑手控车、手部发力、悬挂压缩与机械震动；" +
        "4）侧向英雄中景拍车手冲坡腾空飞跃，画面状态接近图一，泥土在逆光中大面积飞散；" +
        "5）腾空近景帅气细节，突出头盔护目镜、手部控把、轮胎悬空或车身侧面局部；" +
        "6）中景跟拍落地，悬挂压缩回弹，随后继续沿土坡赛道高速冲刺收尾。" +
        "全片同一名骑手、同一辆车、同一条赛道，镜头景别和角度区分清楚，不重复，动作连贯,画面有真实越野跟拍抖动感、速度感、扬土感和夕阳逆光竞技氛围。"

    // Example resource URLs
    refImage := "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_4k.png"

    // Output video parameters
    generateAudio := true
    videoResolution := "4k"
    videoRatio := "adaptive"
    videoDuration := int64(15)
    showWatermark := true

    // 1. Create video generation task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model:         modelID,
        GenerateAudio: volcengine.Bool(generateAudio),
        Resolution:    volcengine.String(videoResolution),
        Ratio:         volcengine.String(videoRatio),
        Duration:      volcengine.Int64(videoDuration),
        Watermark:     volcengine.Bool(showWatermark),
        Content: []*model.CreateContentGenerationContentItem{
            {
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String(prompt),
            },
            {
                Type: model.ContentGenerationContentItemType("image_url"),
                ImageURL: &model.ImageURL{
                    URL: refImage,
                },
                Role: volcengine.String("reference_image"),
            },
        },
    }

    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v\n", err)
        return
    }

    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s\n", taskID)

    // 2. Poll task status
    pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v\n", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s\n", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<span id="c40ed3ef"></span>
## 使用联网搜索

> 联网搜索能力仅适用于纯文本输入


通过配置 tools. **type** 参数为`web_search`即可使用联网搜索工具。


* 开启联网搜索后，模型会根据用户的提示词自主判断是否搜索互联网内容（如商品、天气等）。可提升生成视频的时效性，但也会增加一定的时延。

* 实际搜索次数可通过 [查询视频生成任务 API](https://www.volcengine.com/docs/82379/1521309) 返回的 usage.tool_usage. **web_search** 字段获取，如果为 0 表示未搜索。



<span aceTableMode="list" aceTableWidth="5,5"></span>
|输入：文本 |输出 |
|---|---|
|微距镜头对准叶片上翠绿的玻璃蛙。焦点逐渐从它光滑的皮肤，转移到它完全透明的腹部，一颗鲜红的心脏正在有力地、规律地收缩扩张。<br><br><div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div><br><br><br><div data-tips="true" data-tips-type="tip">联网搜索玻璃蛙的容貌特征。</div><br> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/afad79fc76a34d1fbe7b2c809d1e19f1" controls></video><br> |



<Tabs>
<Tab zoneid="n8dvykZqzv" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time  
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 
# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)
if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID 
        content=[
            {
                # text prompt
                "type": "text",
                "text": "微距镜头对准叶片上翠绿的玻璃蛙。焦点逐渐从它光滑的皮肤，转移到它完全透明的腹部，一颗鲜红的心脏正在有力地、规律地收缩扩张。"
            }
        ],
        ratio="16:9",
        duration=11,
        watermark=False,
        tools=[{"type": "web_search"}],
    )
    print(create_result)
    
    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)
```



</Tab>
<Tab zoneid="aja5cZzJ8x" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.Collections;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
           
    public static void main(String[] args) {
        String model = "doubao-seedance-2-0-260128"; // Replace with Model ID
        String prompt = "微距镜头对准叶片上翠绿的玻璃蛙。焦点逐渐从它光滑的皮肤，转移到它完全透明的腹部，一颗鲜红的心脏正在有力地、规律地收缩扩张。";
        
        Boolean generateAudio = true;
        String videoRatio = "16:9";
        Long videoDuration = 11L;
        Boolean showWatermark = true;
        
        // Create ContentGenerationTool
        CreateContentGenerationTaskRequest.ContentGenerationTool webSearchTool = new CreateContentGenerationTaskRequest.ContentGenerationTool();
        webSearchTool.setType("web_search");
        
        System.out.println("----- create request -----");
        List<Content> contents = new ArrayList<>();
        
        // text prompt
        contents.add(Content.builder()
                .type("text")
                .text(prompt)
                .build());
         
        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(modelId)
                .content(contents)
                .generateAudio(generateAudio)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(showWatermark)
                .tools(Collections.singletonList(webSearchTool))
                .build();
        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);
        // Get the details of the task
        String taskId = createResult.getId();
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();
        
        // Polling query section
        System.out.println("----- polling task status -----");
        while (true) {
            try {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();
                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    System.out.println("Error: " + getResponse.getStatus());
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                System.err.println("Polling interrupted");
                break;
            }
        }
    }
}
```



</Tab>
<Tab zoneid="XBZUXCKNmr" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    
    // Model ID
    modelID := "doubao-seedance-2-0-260128"
    // Text prompt
    prompt := "微距镜头对准叶片上翠绿的玻璃蛙。焦点逐渐从它光滑的皮肤，转移到它完全透明的腹部，一颗鲜红的心脏正在有力地、规律地收缩扩张。"

    // Output video parameters
    generateAudio := true
    videoRatio := "adaptive"
    videoDuration := int64(11)
    showWatermark := true

    // Create ContentGenerationTool
    tools := []*model.ContentGenerationTool{
        {Type: model.ToolTypeWebSearch},
    }

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model:     modelID,
        GenerateAudio: volcengine.Bool(generateAudio),
        Ratio:     volcengine.String(videoRatio),
        Duration:  volcengine.Int64(videoDuration),
        Watermark: volcengine.Bool(showWatermark),
        Tools:     tools,
        Content: []*model.CreateContentGenerationContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String(prompt),
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v\n", err)
        return
    }

    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s\n", taskID)

    // 2. Poll task status
    pollTaskStatus(ctx, client, taskID)
}

    // poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v\n", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s\n", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<span id="17c64b2e"></span>
## 更多能力

Seedance 2.0 系列模型也支持文生视频、首帧图生视频、首尾帧图生视频、自定义视频输出规格（包括：分辨率、宽高比、视频时长、视频中是否包含水印）等通用基础能力，详情请参见 [视频生成教程](https://www.volcengine.com/docs/82379/2298881)。

<span id="5c67c9a1"></span>
# 便利创作

Seedance 2.0 系列模型不支持直接上传含有真人人脸的参考图/视频。为便利创作者使用肖像，平台推出了以下解决方案。


<span aceTableMode="list" aceTableWidth="2,4"></span>
|方案 |介绍 |
|---|---|
|[信任模型产物作为输入素材](https://www.volcengine.com/docs/82379/2291680#341d7f71) |本账号下部分模型生成的含人脸原始产物可作为输入素材，再次调用 Seedance 2.0 系列模型进行二次创作，不会触发输入审核拦截。 |
|[使用预置虚拟人像](https://www.volcengine.com/docs/82379/2291680#2bf01416) |平台预置虚拟人像库，为创作者提供免费、合规、丰富多样的肖像素材。适用于需真人风格人脸但无需指定具体人物，追求零合规风险、快速创作的场景。 |
|[使用已授权真人素材](https://www.volcengine.com/docs/82379/2291680#f952d0c3) |支持使用已获得授权的真人肖像素材进行视频生成。 |


<span id="341d7f71"></span>
## 信任模型产物作为输入素材

Seedance 2.0 系列模型不支持直接上传含有真人人脸的参考图/视频。为了便利创作者在含人脸场景的二次创作需求，方舟平台信任以下模型生成的含人脸产物，您可使用 **本账号下近30天内由以下模型生成的含人脸原始产物** ，作为输入素材，再次调用 Seedance 2.0 系列模型进行二次创作。


|信任产物范围 |生效时间<br><br>> 信任该时间之后生成的产物 |有效期<br><br>> 从产物生成时间开始计算 |
|---|---|---|
|Seedance 2.0 系列 生成的含人脸视频 |2026年03月11日起 |30天 |
|Seedance 2.0 系列 生成的含人脸视频对应的尾帧图片 |2026年04月16日起 |30天 |
|[Seedream 5.0 lite 文生图](https://www.volcengine.com/docs/82379/1824121#9695d195)得到的含人脸图片 |2026年04月16日起 |30天 |


<div data-tips="true" data-tips-type="warning" data-tips-is-title="true">注意</div>



* <div data-tips="true" data-tips-type="warning">仅信任方舟平台的产物，不支持跨平台使用。</div>


* <div data-tips="true" data-tips-type="warning">仅信任同账号下的产物，不支持跨账号使用。</div>


* <div data-tips="true" data-tips-type="warning">仅信任模型原始产物，二次剪辑或超过有效期后均不可使用。</div>


* <div data-tips="true" data-tips-type="warning">压缩或转发文件易引发信任失效，建议直接将模型原始产物转存至 TOS 使用。</div>


* <div data-tips="true" data-tips-type="warning">仅对输入的产物进行信任，输出依然有可能因命中方舟安全审核策略而失败，详情参见 <a href="https://www.volcengine.com/docs/82379/1299023">错误码</a>。</div>


* <div data-tips="true" data-tips-type="warning">信任仅对命中人脸审核生效，对于不含人脸场景，模型产物不存在受信问题，支持自由剪辑后进行二次创作。</div>




<span aceTableMode="list" aceTableWidth="7,16"></span>
|输入：同账号生成的视频 |输出 |
|---|---|
|<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/24e27818aeb644b6942c2cbc949ddc86" controls></video><br><br><br>> [使用预置虚拟人像](https://www.volcengine.com/docs/82379/2291680#2bf01416)示例生成的视频 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/44d52b9f0768460c8c86b81d2df40350" controls></video><br><br><br>> 输入：将面霜的颜色修改为白色。<br><br>> ratio 修改为16:9 |



<Tabs>
<Tab zoneid="mJ4q6qdfQN" title="Python">
<TabTitle>Python</TabTitle>

1. 首次生视频，并获取视频 URL。此处直接用[使用预置虚拟人像](https://www.volcengine.com/docs/82379/2291680#2bf01416)示例生成的视频。

2. 对 Seedance 2.0 生成的视频进行再次编辑。视频原始 URL 的有效期仅 24 小时，本示例将原始视频转存至 TOS 使用。


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">视频原始 URL 的有效期仅 24 小时，实际使用时，建议您提前转存视频文件。推荐配置火山引擎 TOS 提供的数据订阅功能，将您的视频产物自动转存到自己的 TOS 桶中，便于长期备份或二次加工。详细介绍请参见 <a href="https://www.volcengine.com/docs/6349/2280949?lang=zh">TOS 数据订阅</a>。</div>


```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID 
        content=[
            {
                "type": "text",
                "text": "将面霜的颜色修改为白色。"
            },                
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_video/video_by_sd2.mp4"
                },
                "role": "reference_video"
            },
        ],
        generate_audio=True,
        ratio="16:9",
        duration=11,
        watermark=True,
    )
    print(create_result)
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
```



</Tab>
<Tab zoneid="WVBsFDoV99" title="Java">
<TabTitle>Java</TabTitle>

1. 首次生视频，并获取视频 URL。此处直接用[使用预置虚拟人像](https://www.volcengine.com/docs/82379/2291680#2bf01416)示例生成的视频。

2. 对 Seedance 2.0 生成的视频进行再次编辑。视频原始 URL 的有效期仅 24 小时，本示例将原始视频转存至 TOS 使用。


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">视频原始 URL 的有效期仅 24 小时，实际使用时，建议您提前转存视频文件。推荐配置火山引擎 TOS 提供的数据订阅功能，将您的视频产物自动转存到自己的 TOS 桶中，便于长期备份或二次加工。详细介绍请参见 <a href="https://www.volcengine.com/docs/6349/2280949?lang=zh">TOS 数据订阅</a>。</div>


```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
           
    public static void main(String[] args) {
        
        // Model ID
        final String modelId = "doubao-seedance-2-0-260128";
        // Text prompt
        final String prompt = "将面霜的颜色修改为白色。";
        
        // Example resource URLs
        final String refVideo = "https://ark-project.tos-cn-beijing.volces.com/doc_video/video_by_sd2.mp4";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "16:9";      
        final long videoDuration = 11L;          
        final boolean showWatermark = true;

        System.out.println("----- create request -----");
        // Build request content
        List<Content> contents = new ArrayList<>();
        
        // 1. Text prompt
        contents.add(Content.builder()
                .type("text")
                .text(prompt)
                .build());
                
        // 2. Reference video
        contents.add(Content.builder()
                .type("video_url")
                .videoUrl(CreateContentGenerationTaskRequest.VideoUrl.builder()
                        .url(refVideo)
                        .build())
                .role("reference_video")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(showWatermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        System.out.println("----- polling task status -----");
        try {
            while (true) {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    if (getResponse.getError() != null) {
                        System.out.println("Error: " + getResponse.getError().getMessage());
                    }
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            System.err.println("Polling interrupted");
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
        } finally {
            service.shutdownExecutor();
        }
    }
}
```



</Tab>
<Tab zoneid="ZEV682kpBQ" title="Go">
<TabTitle>Go</TabTitle>

1. 首次生视频，并获取视频 URL。此处直接用[使用预置虚拟人像](https://www.volcengine.com/docs/82379/2291680#2bf01416)示例生成的视频。

2. 对 Seedance 2.0 生成的视频进行再次编辑。视频原始 URL 的有效期仅 24 小时，本示例将原始视频转存至 TOS 使用。


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">视频原始 URL 的有效期仅 24 小时，实际使用时，建议您提前转存视频文件。推荐配置火山引擎 TOS 提供的数据订阅功能，将您的视频产物自动转存到自己的 TOS 桶中，便于长期备份或二次加工。详细介绍请参见 <a href="https://www.volcengine.com/docs/6349/2280949?lang=zh">TOS 数据订阅</a>。</div>


```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Initialize Ark client
    client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()

    // Model ID
    modelID := "doubao-seedance-2-0-260128"
    // Text prompt
    prompt := "将面霜的颜色修改为白色。"

    // Example resource URLs
    refVideo1 := "https://ark-project.tos-cn-beijing.volces.com/doc_video/video_by_sd2.mp4"

    // Output video parameters
    generateAudio := true
    videoRatio := "16:9"
    videoDuration := int64(11)
    showWatermark := true

    // 1. Create video generation task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model:         modelID,
        GenerateAudio: volcengine.Bool(generateAudio),
        Ratio:         volcengine.String(videoRatio),
        Duration:      volcengine.Int64(videoDuration),
        Watermark:     volcengine.Bool(showWatermark),
        Content: []*model.CreateContentGenerationContentItem{
            {
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String(prompt),
            },
            {
                Type: model.ContentGenerationContentItemType("video_url"),
                VideoURL: &model.VideoUrl{
                    Url: refVideo1,
                },
                Role: volcengine.String("reference_video"),
            },
        },
    }

    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v\n", err)
        return
    }

    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s\n", taskID)

    // 2. Poll task status
    pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v\n", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s\n", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


&nbsp;

<span id="2bf01416"></span>
## 使用预置虚拟人像

对写实风格视频，可通过虚拟人像库预置人像来控制角色样貌。每个素材对应一个独立素材 ID (asset ID)， 在 **content.<模态\>_url.url** 字段中传入 `asset://<asset ID>` 即可生成视频。

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">开通虚拟人像库，浏览及检索虚拟人像请参见<a href="https://www.volcengine.com/docs/82379/2223965">虚拟人像库</a>。</div>



<span aceTableMode="list" aceTableWidth="3,3,4"></span>
|输入：文本 |输入：虚拟人像、图片 |输出 |
|---|---|---|
|固定机位，近景镜头，清新自然风格。在室内自然光下， **图片1** 中美妆博主面带笑容，向镜头介绍 **图片2** 中的面霜。博主将手里的面霜展示给镜头，开心地说“挖到本命面霜了！”；接着她一边用手指轻轻蘸取面霜展示那种软糯感，一边说“质地像云朵一样软糯，一抹就吸收”；最后她把面霜涂抹在脸颊上，展示着水润透亮的皮肤，同时自信地说“熬夜急救、补水保湿全搞定”。要求画面中人物居中，完整展示人物的整个脑袋和上半身，始终对焦人脸，人脸始终清晰，纯净无任何字幕。<br><br><div data-tips="true" data-tips-type="warning" data-tips-is-title="true">注意</div><br><br><br><div data-tips="true" data-tips-type="warning">Asset ID 仅用来向模型传入素材，提示词中仍需使用" <strong>素材类型+序号</strong> ”格式引用素材，序号为请求体中该素材在同类素材中的排序。</div><br><br><br><div data-tips="true" data-tips-type="warning">正确用法： <strong>图片1</strong> 中美妆博主</div><br><br><br><div data-tips="true" data-tips-type="warning">错误用法：asset\-2026\*\*\*\*是美妆博主</div><br> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/946509d1f37f476c9ff29e0adaf187eb~tplv-goo7wpa0wc-image.image) </span><br><br>> 虚拟人像<br><br><br><span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/791b783fc6cd4394b13f41b66b5ff461~tplv-goo7wpa0wc-image.image) </span><br><br>> 产品图像 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/0bd96f702bdf48bab1a9505710d9e1f9" controls></video><br> |



<Tabs>
<Tab zoneid="njI3b0R8bj" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark 

client = Ark(
    # The base URL for model invocation
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID 
        content=[
            {
                "type": "text",
                "text": "固定机位，近景镜头，清新自然风格。在室内自然光下，图片1中美妆博主面带笑容，向镜头介绍图片2中的面霜。博主将手里的面霜展示给镜头，开心地说“挖到本命面霜了！”；接着她一边用手指轻轻蘸取面霜展示那种软糯感，一边说“质地像云朵一样软糯，一抹就吸收”；最后她把面霜涂抹在脸颊上，展示着水润透亮的皮肤，同时自信地说“熬夜急救、补水保湿全搞定”。要求画面中人物居中，完整展示人物的整个脑袋和上半身，始终对焦人脸，人脸始终清晰，纯净无任何字幕。"
            },        
            {
                "type": "image_url",
                "image_url": {
                    "url": "asset://asset-20260401123823-6d4x2"
                },
                "role": "reference_image"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_edit_pic1.jpg"
                },
                "role": "reference_image"
            },
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=11,
        watermark=True,
    )
    print(create_result)

    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 30 seconds...")
            time.sleep(30)
```



</Tab>
<Tab zoneid="kAqzAhTiLJ" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {

    // Client initialization
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();
           
    public static void main(String[] args) {
        
        // Model ID
        final String modelId = "doubao-seedance-2-0-260128";
        // Text prompt
        final String prompt = "固定机位，近景镜头，清新自然风格。在室内自然光下，图片1中美妆博主面带笑容，向镜头介绍图片2中的面霜。博主将手里的面霜展示给镜头，开心地说“挖到本命面霜了！”；接着她一边用手指轻轻蘸取面霜展示那种软糯感，一边说“质地像云朵一样软糯，一抹就吸收”；最后她把面霜涂抹在脸颊上，展示着水润透亮的皮肤，同时自信地说“熬夜急救、补水保湿全搞定”。要求画面中人物居中，完整展示人物的整个脑袋和上半身，始终对焦人脸，人脸始终清晰，纯净无任何字幕。";
        
        // Example resource URLs
        final String refImage1 = "asset://asset-20260401123823-6d4x2";
        final String refImage2 = "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_edit_pic1.jpg";

        // Output video parameters
        final boolean generateAudio = true;
        final String videoRatio = "adaptive";      
        final long videoDuration = 11L;          
        final boolean showWatermark = true;

        System.out.println("----- create request -----");
        // Build request content
        List<Content> contents = new ArrayList<>();
        
        // 1. Text prompt
        contents.add(Content.builder()
                .type("text")
                .text(prompt)
                .build());
                
        // 2. Reference image 1
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url(refImage1)
                        .build())
                .role("reference_image")
                .build());

        // 3. Reference image 2
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url(refImage2)
                        .build())
                .role("reference_image")
                .build());

        // Create video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .generateAudio(generateAudio)
                .model(modelId)
                .content(contents)
                .ratio(videoRatio)
                .duration(videoDuration)
                .watermark(showWatermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println("Task Created: " + createResult);

        // Get task details and poll status
        String taskId = createResult.getId();
        pollTaskStatus(taskId);
    }

    /**
     * Poll task status
     * @param taskId Task ID
     */

    private static void pollTaskStatus(String taskId) {
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        System.out.println("----- polling task status -----");
        try {
            while (true) {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();

                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    if (getResponse.getError() != null) {
                        System.out.println("Error: " + getResponse.getError().getMessage());
                    }
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...%n", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            System.err.println("Polling interrupted");
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
        } finally {
            service.shutdownExecutor();
        }
    }
}
```



</Tab>
<Tab zoneid="V8cwnoECTk" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Initialize Ark client
    client := arkruntime.NewClientWithApiKey(
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()

    // Model ID
    modelID := "doubao-seedance-2-0-260128"
    // Text prompt
    prompt := "固定机位，近景镜头，清新自然风格。在室内自然光下，图片1中美妆博主面带笑容，向镜头介绍图片2中的面霜。博主将手里的面霜展示给镜头，开心地说“挖到本命面霜了！”；接着她一边用手指轻轻蘸取面霜展示那种软糯感，一边说“质地像云朵一样软糯，一抹就吸收”；最后她把面霜涂抹在脸颊上，展示着水润透亮的皮肤，同时自信地说“熬夜急救、补水保湿全搞定”。要求画面中人物居中，完整展示人物的整个脑袋和上半身，始终对焦人脸，人脸始终清晰，纯净无任何字幕。"

    // Example resource URLs
    refImage1 := "asset://asset-20260401123823-6d4x2"
    refImage2 := "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_edit_pic1.jpg"

    // Output video parameters
    generateAudio := true
    videoRatio := "adaptive"
    videoDuration := int64(11)
    showWatermark := true

    // 1. Create video generation task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model:         modelID,
        GenerateAudio: volcengine.Bool(generateAudio),
        Ratio:         volcengine.String(videoRatio),
        Duration:      volcengine.Int64(videoDuration),
        Watermark:     volcengine.Bool(showWatermark),
        Content: []*model.CreateContentGenerationContentItem{
            {
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String(prompt),
            },
            {
                Type: model.ContentGenerationContentItemType("image_url"),
                ImageURL: &model.ImageURL{
                    URL: refImage1,
                },
                Role: volcengine.String("reference_image"),
            },
            {
                Type: model.ContentGenerationContentItemType("image_url"),
                ImageURL: &model.ImageURL{
                    URL: refImage2,
                },
                Role: volcengine.String("reference_image"),
            },
        },
    }

    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v\n", err)
        return
    }

    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s\n", taskID)

    // 2. Poll task status
    pollTaskStatus(ctx, client, taskID)
}

// poll task status
func pollTaskStatus(ctx context.Context, client *arkruntime.Client, taskID string) {
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v\n", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d\n", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s\n", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<span id="f952d0c3"></span>
## 使用已授权真人素材

通过真人认证和本人授权后，可将该真人的相关素材（例如该真人的图片、视频、音频）上传至方舟。素材入库成功后，每个素材将获得一个独立素材 ID (asset ID)， 在 **content.<模态\>_url.url** 字段中传入 `asset://<asset ID>`即可使用该素材生成视频。真人认证及素材入库流程请参见[录入真人形象素材](https://www.volcengine.com/docs/82379/2315856)。

```text
...
"content": [
         {
            "type": "text",
            "text": "<your prompt>"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "asset://<asset ID>"
            },
            "role": "reference_image"
        },
        {
            "type": "video_url",
            "video_url": {
                "url": "asset://<asset ID>"
            },
            "role": "reference_video"
        },
        {
            "type": "audio_url",
            "audio_url": {
                "url": "asset://<asset ID>"
            },
            "role": "reference_audio"
        }
    ]
...
```


&nbsp;

<span id="2d8359f8"></span>
# 提示词技巧

<span id=".5o-Q56S66K-NLXNraWxs"></span>
## 提示词 Skill

平台提供 **Seedance 2.0 提示词优化技能** ，方便您对提示词进行调优。


* **配置方式** ：可将技能文件配置到 Code Agent / AI Agent 中使用。以 OpenClaw 为例，下载该 SKILL.md 文件，复制完整内容至对话输入框中，并发送”请帮我安装这个技能”，等待工具自动完成安装。

* **使用方式** ：在 AI 对话框输入 `/sd2-pe + 你的提示词内容`，开始调试提示词。


<Attachment link="https://arkdoc.tos-cn-beijing.volces.com/files/video-generation/SKILL.md" name="SKILL.md">SKILL.md</Attachment>


<span id=".5o-Q56S66K-N6KeE5YiZ"></span>
## 提示词规则


* 提示词中必须使用" **素材类型+序号** ”格式引用素材，序号为请求体中该素材在同类素材中的排序。例如 「图片 n」指代`content`数组中第 n 个`type="image_url"`的参考图片（按数组顺序从1开始计数）。 **注意不支持使用 Asset ID 指代素材** 。

* 不同任务的提示词公式及详细规则请参见 [Doubao Seedance 2.0 系列提示词指南](https://www.volcengine.com/docs/82379/2222480)。


<span id="66cb028f"></span>
# 使用限制

参见[使用限制](https://www.volcengine.com/docs/82379/1366799#66cb028f)。

<span id="d21b3c92"></span>
# 常见问题

<span id="4k_player"></span>
## 4k 播放器兼容性说明

以下为各平台浏览器及播放器对 Seedance 2.0 生成的 4K H.265/HEVC 10bit 视频的播放兼容性测试结论，实际效果可能因设备配置有所差异。

**推荐使用：** 


* **macOS 端** ：浏览器推荐 Safari、Chrome，播放器推荐 VLC、mpv、QuickTime Player

* **Windows 端** ：浏览器推荐 Edge、Chrome，播放器推荐 VLC、mpv


<span id=".d2luZG93cy3lubPlj7A="></span>
### Windows 平台


<Tabs>
<Tab zoneid="RwdZAEfkJI" title="浏览器">
<TabTitle>浏览器</TabTitle>


|浏览器 |支持情况 |
|---|---|
|Chrome |有条件支持 |
|Edge |有条件支持 |
|Firefox |有条件支持 |
|360 浏览器 |有条件支持 |
|QQ 浏览器 |有条件支持 |
|Opera |有条件支持 |



</Tab>
<Tab zoneid="R72yYa8I8i" title="播放器">
<TabTitle>播放器</TabTitle>


|播放器 |支持情况 |
|---|---|
|VLC |支持 |
|系统「电影和电视」 |有条件支持 |
|PotPlayer |有条件支持 |
|迅雷影音 |支持 |
|QQ 影音 |有条件支持 |
|MPC\-HC / MPC\-BE |有条件支持 |
|mpv |支持 |
|KMPlayer |支持 |



</Tab>
</Tabs>


> **有条件支持说明** ：需具备较高的硬件解码能力。已知在 Intel i7 + NVIDIA RTX 4070 + Windows 11 及更高配置下可正常播放，其他配置建议以实际测试为准。


<span id=".bWFjb3Mt5bmz5Y-w"></span>
### macOS 平台


<Tabs>
<Tab zoneid="n0v3u5YJEI" title="浏览器">
<TabTitle>浏览器</TabTitle>


|浏览器 |支持情况 |
|---|---|
|Safari |支持 |
|Chrome |有条件支持 |
|Edge |有条件支持 |
|Firefox |有条件支持 |
|Opera |有条件支持 |



</Tab>
<Tab zoneid="n6Zl0zwFq0" title="播放器">
<TabTitle>播放器</TabTitle>


|播放器 |支持情况 |
|---|---|
|VLC |支持 |
|QuickTime Player |支持 |
|IINA |支持 |
|mpv |支持 |
|Infuse |支持 |
|Kodi |有条件支持 |



</Tab>
</Tabs>


> **有条件支持说明** ：需具备较高的硬件解码能力。已知 Apple M2 及以上机型可正常播放，M1 及以下机型建议以实际测试为准。


<span id="1df655fb"></span>
## 视频画面存在跳变

**典型现象**

**首帧图生视频** 、 **首尾帧图生视频** 场景中，生成视频部分帧出现画面拉伸、压缩等跳变问题。

**根因分析**

输入图片与输出视频的分辨率宽高不一致，引发视频画面帧间跳变。

**解决方案**


1. 裁剪输入图片：参考 Seedance 2.0 系列模型支持的宽高像素值表格（见 [创建视频生成任务 API](https://www.volcengine.com/docs/82379/1520757) ratio 字段），将输入图片裁剪为目标宽高像素值。

2. 将 API 的 **ratio** 字段设置为`adaptive`。

3. 使用 Seedance 2.0 系列模型重新发起首帧/首尾帧图生视频任务。

## 视频生成教程

Seedance 模型具备出色的语义理解能力，可根据用户输入的文本、图片、视频、音频等多模态内容，快速生成优质的视频片段。本文为您介绍视频生成模型的通用基础能力，指导您调用 [Video Generation API](https://www.volcengine.com/docs/82379/1520758) 生成视频。如需了解 Seedance 2.0 系列模型的最新能力，请参见 [Doubao Seedance 2.0 系列教程](https://www.volcengine.com/docs/82379/2291680)。

<span id="a06d249e"></span>
# 效果预览

访问 [模型卡片](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0) 查看更多示例。


<span aceTableMode="list" aceTableWidth="2,2,4,4"></span>
|场景 |输入：提示词 |输入：图片、视频、音频 |输出 |
|---|---|---|---|
|多模态参考<br><br>> 可参考图、<br><br>> 视频和音频 |以 **图片1** 为首帧，画面放大至飞机舷窗外，一团团云朵缓缓飘至画面中，其中一朵为彩色糖豆点缀的云朵，始终在画面中居中，然后缓缓变形为 **图片2** 中的冰淇淋，镜头推远回到机舱内，坐在窗边的 **图片3** 中的角色伸手从窗外拿进冰淇淋，吃了一口，嘴巴上沾满奶油，脸上洋溢出甜蜜的笑容，此时视频配音为 **音频1** |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/52bdd8074d41430b97afb773ac6acb91~tplv-goo7wpa0wc-image.image) </span><br><br><Attachment link="https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/8d84cc7bbb5f486cbe66c26ddd1f6e47~tplv-goo7wpa0wc-image.image" name="冰淇淋 .mp3">冰淇淋 .mp3</Attachment><br> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/8eaeafa52ae04afe8d8894be0145c8c8" controls></video><br> |
|编辑视频<br><br>> 替换视频主体、视频中对象增删改、局部画面重绘/修复等 |将 **视频1** 中的房子外立面墙壁刷成蓝色，天气和光线参考 **图片1** 的雪天 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/0751d1ba97664456893058e914a1b44a" controls></video><br><br><br><span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/666b1aa0e24143b285cf2325ad90de77~tplv-goo7wpa0wc-image.image) </span> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/5c17f8570a3943ceaa0c806aeffcbac9" controls></video><br> |
|延长视频<br><br>> 向前或者向后延长视频，或多个视频片段串联成一个连贯视频 |将 **视频1** 向后延长，11秒视频，汽车丝滑行驶到一片沙漠绿洲，背景音乐使用 **音频1** |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/7d84f0e0149348f598c8df548195b1c1" controls></video><br><br><br><Attachment link="https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/245274e557ec477d92359c6468cc7ca2~tplv-goo7wpa0wc-image.image" name="汽车背景音.mp3">汽车背景音.mp3</Attachment><br> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/37e14c2c6b994ef6821b1bebb8c1bd47" controls></video><br> |
|首帧图生视频 |镜头围绕人物推镜头拉近，特写人物面部，她正在用京剧唱腔唱“月移花影，疑是玉人来”，唱词充满情感，唱腔充满传统京剧特有的韵味与技巧，完美体现了花旦角色的内心世界 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/bf9e55ee68e34671abbb12942aceb91a~tplv-goo7wpa0wc-image.image) </span> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/2fe3d82baa1642b1926007968a44e022" controls></video><br> |
|首尾帧生视频 |360度环绕运镜 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f8fc1008f23a4908b7c897e8b7eb87df~tplv-goo7wpa0wc-image.image) </span> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/9cb7768701564b73ac45616097452338" controls></video><br> |


<span id="fd30cc1a"></span>
# 新手入门

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">下文详细介绍使用不同编程语言调用视频生成 API 的示例代码。</div>



* <div data-tips="true" data-tips-type="tip">若您是编程零基础用户，推荐使用 <a href="https://console.volcengine.com/ark/region:ark+cn-beijing/experience/vision?modelId=doubao-seedance-2-0-260128&tab=GenVideo">控制台体验中心</a>，包含丰富的模板库，可一键生成同款视频，无需编写代码即可快速上手创作。</div>


* <div data-tips="true" data-tips-type="tip">若您想快速体验 API 调用，推荐使用<a href="https://api.volcengine.com/api-explorer/?action=CreateContentsGenerationsTasks&groupName=%E8%A7%86%E9%A2%91%E7%94%9F%E6%88%90API&serviceCode=ark&version=2024-01-01">API Explorer</a>，内置预设参数模板，可一键发起 API 调用；同时也支持灵活调整参数（例如设置视频水印等），满足多样化的测试和使用场景。</div>


* <div data-tips="true" data-tips-type="tip">若您想真正开始编程开发，但苦于搭建开发环境、依赖安装等问题，推荐阅读 <a href="https://www.volcengine.com/docs/82379/2291680">seedance 2.0 新手入门</a>。</div>



视频生成是一个异步过程：


1. 成功调用 `POST /contents/generations/tasks` 接口后，API 将返回一个任务 ID 。

2. 您可以轮询 `GET /contents/generations/tasks/{id}` 接口，直到任务状态变为 `succeeded`；或者使用 Webhook 自动接收视频生成任务的状态变化。

3. 任务完成后，您可在 content. **video_url** 字段处，下载最终生成的 MP4 文件。


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">方舟平台的新用户？获取 API Key 及 开通模型等准备工作，请参见 <a href="https://www.volcengine.com/docs/82379/1399008">快速入门</a>。</div>


<span id="34b10d6d"></span>
## Step1: 创建视频生成任务

通过 `POST /contents/generations/tasks` 创建视频生成任务。


<Tabs>
<Tab zoneid="ZA1zzSpb2R" title="Curl">
<TabTitle>Curl</TabTitle>

```Bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-2-0-260128",
    "content": [
        {
            "type": "text",
            "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"
            }
        }
    ],
    "generate_audio": true,
    "ratio": "adaptive",
    "duration": 5,
    "watermark": false
}'
```



</Tab>
<Tab zoneid="Ycjgz6xBDW" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
from volcenginesdkarkruntime import Ark

# Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
client = Ark(api_key=os.environ.get("ARK_API_KEY"))

if __name__ == "__main__":
    print("----- create request -----")
    resp = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID
        content=[
            {
                "text": (
                    "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动"
                ),
                "type": "text"
            },
            {
                "image_url": {
                    "url": (
                        "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"
                    )
                },
                "type": "image_url"
            }
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=5,
        watermark=False,
    )

    print(resp)
```



</Tab>
<Tab zoneid="Vpf5ClRfJV" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {
        String model = "doubao-seedance-2-0-260128"; // Replace with Model ID
        Boolean generateAudio = true;
        String ratio = "adaptive";
        Long duration = 5L;
        Boolean watermark = false;
        System.out.println("----- create request -----");
        List<Content> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(Content.builder()
                .type("text")
                .text("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声")
                .build());
        // The URL of the first frame image
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url("https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png")
                        .build())
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .generateAudio(generateAudio)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);

        service.shutdownExecutor();
    }
}
```



</Tab>
<Tab zoneid="oj5nF7bSKJ" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-2-0-260128"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        GenerateAudio: volcengine.Bool(true),
        Ratio:         volcengine.String("adaptive"),
        Duration:      volcengine.Int64(5),
        Watermark:     volcengine.Bool(false),
        Content: []*model.CreateContentGenerationContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声"),
            },
            {
                // The URL of the first frame image
                Type: model.ContentGenerationContentItemTypeImage,
                ImageURL: &model.ImageURL{
                    URL: "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png",
                },
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)
}
```



</Tab>
</Tabs>


请求成功后，系统将返回一个任务 ID。

```JSON
{
  "id": "cgt-2025******-****"
}
```


<span id="a4fa0cc8"></span>
## Step2: 查询视频生成任务

利用创建视频生成任务时返回的 ID ，您可以查询视频生成任务的详细状态与结果。此接口会返回任务的当前状态（如 `queued` 、`running` 、 `succeeded` 等）以及生成的视频相关信息（如视频下载链接、分辨率、时长等）。

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">因模型、API负载和视频输出规格的不同，视频生成的过程可能耗时较长。为高效管理这一过程，您可以通过轮询 API 接口（详见 <a href="https://www.volcengine.com/docs/82379/1366799#c637f771">基础使用</a> 和 <a href="https://www.volcengine.com/docs/82379/1366799#e190e738">进阶使用</a> 部分的 SDK 示例）来请求状态更新，或通过 <a href="https://www.volcengine.com/docs/82379/1366799#caf01f12">使用 Webhook 通知</a> 接收通知。</div>



<Tabs>
<Tab zoneid="ilPu8lmSqs" title="Curl">
<TabTitle>Curl</TabTitle>

```Bash
# Replace cgt-2025**** with the ID acquired from "Create Video Generation Task".

curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-2025**** \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY"
```



</Tab>
<Tab zoneid="sy1fZqfsfn" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
from volcenginesdkarkruntime import Ark

# Get API Key: https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
client = Ark(api_key=os.environ.get("ARK_API_KEY"))

if __name__ == "__main__":
    resp = client.content_generation.tasks.get(
        task_id="cgt-2025****",
    )
    print(resp)
```



</Tab>
<Tab zoneid="pvvVflbjqG" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.volcengine.ark.runtime.model.content.generation.GetContentGenerationTaskRequest;
import com.volcengine.ark.runtime.service.ArkService;
import java.util.concurrent.TimeUnit;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;


public class Sample {

    static String apiKey = System.getenv("ARK_API_KEY");

    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service =
            ArkService.builder()
                    .dispatcher(dispatcher)
                    .connectionPool(connectionPool)
                    .apiKey(apiKey)
                    .build();

    public static void main(String[] args) throws JsonProcessingException {
        String taskId = "cgt-2025****";

        GetContentGenerationTaskRequest req = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();


        service.getContentGenerationTask(req).toString();
        System.out.println(service.getContentGenerationTask(req));

        service.shutdownExecutor();
    }
}
```



</Tab>
<Tab zoneid="LOCbDFQtzE" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
        "context"
        "fmt"
        "os"

        "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
        "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
)


func main() {
        client := arkruntime.NewClientWithApiKey(os.Getenv("ARK_API_KEY"))
        ctx := context.Background()

        req := model.GetContentGenerationTaskRequest{
                ID: "cgt-2025****",
        }
        resp, err := client.GetContentGenerationTask(ctx, req)
        if err != nil {
                fmt.Printf("get content generation task error: %v\n", err)
                return
        }
        fmt.Printf("%+v\n", resp)
}
```



</Tab>
</Tabs>


当任务状态变为 succeeded 后，您可在 content. **video_url** 字段处，下载最终生成的视频文件。

```JSON
{
    "id": "cgt-2025****",
    "model": "doubao-seedance-2-0-260128",
    "status": "succeeded",
    "content": {
        // Video download URL (file format is MP4)
        "video_url": "https://ark-content-generation-cn-beijing.tos-cn-beijing.volces.com/****"
    },
    "usage": {
        "completion_tokens": 246840,
        "total_tokens": 246840
    },
    "created_at": 1765510475,
    "updated_at": 1765510559,
    "seed": 58944,
    "resolution": "1080p",
    "ratio": "16:9",
    "duration": 5,
    "framespersecond": 24,
    "service_tier": "default",
    "execution_expires_after": 172800
}
```


<span id="e7b4c498"></span>
# 模型能力

本表格展示所有 Seedance 模型支持的能力，方便您对比和选型。如需了解 Seedance 2.0 系列模型的最新用法，请参见 [Doubao Seedance 2.0 系列教程](https://www.volcengine.com/docs/82379/2291680)。


<span aceTableMode="list" aceTableWidth="3,3,3,2,2,2,2,2"></span>
|模型名称 | |[Seedance 2.0](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0&projectName=default) |[Seedance 2.0 fast](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0-fast&projectName=default) |[Seedance 2.0 mini](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-2-0-mini&projectName=default) |[Seedance 1.5 pro](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-1-5-pro&projectName=default) |[Seedance 1.0 pro](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-1-0-pro&projectName=default) |[Seedance 1.0 pro fast](https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seedance-1-0-pro-fast&projectName=default) |
|---|---|---|---|---|---|---|---|
|Model ID | |doubao\-seedance\-2\-0\-260128 |doubao\-seedance\-2\-0\-fast\-260128 |doubao\-seedance\-2\-0\-mini\-260615 |doubao\-seedance\-1\-5\-pro\-251215 |doubao\-seedance\-1\-0\-pro\-250528 |doubao\-seedance\-1\-0\-pro\-fast\-251015 |
|[文生视频](https://www.volcengine.com/docs/82379/2298881#4e74bcee) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[图生视频-首帧](https://www.volcengine.com/docs/82379/2298881#979b2d28) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[图生视频-首尾帧](https://www.volcengine.com/docs/82379/2298881#0d55ca07) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[多模态参考](https://www.volcengine.com/docs/82379/2291680#50e1b4ea)【New】 |图片参考 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
||视频参考 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
||组合参考<br><br><br>* 图片 + 音频<br><br>* 图片 + 视频<br><br>* 视频 + 音频<br><br>* 图片 + 视频 + 音频 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[编辑视频](https://www.volcengine.com/docs/82379/2291680#75a28782)【New】 | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[延长视频](https://www.volcengine.com/docs/82379/2291680#46d77653)【New】 | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[生成有声视频](https://www.volcengine.com/docs/82379/2298881#979b2d28)<br><br>> "generate_audio": "true" | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[联网搜索工具](https://www.volcengine.com/docs/82379/2291680#c40ed3ef)【New】 | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[样片模式](https://www.volcengine.com/docs/82379/2298881#5acd28c8) | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |
|[返回视频产物对应的尾帧图](https://www.volcengine.com/docs/82379/2298881#141cf7fa)<br><br>> "return_last_frame":<br><br>> "true" | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|[输出视频规格](https://www.volcengine.com/docs/82379/2298881#9fe4cce0) |输出分辨率<br><br>> "resolution": "720p" |480p<br><br>720p<br><br>1080p<br><br>4k（10bit 位深） |480p<br><br>720p |480p<br><br>720p |480p<br><br>720p<br><br>1080p |480p<br><br>720p<br><br>1080p |480p<br><br>720p<br><br>1080p |
| |输出宽高比<br><br>> "ratio":"16:9" |21:9<br><br>16:9<br><br>4:3<br><br>1:1<br><br>3:4<br><br>9:16 |21:9<br><br>16:9<br><br>4:3<br><br>1:1<br><br>3:4<br><br>9:16 |21:9<br><br>16:9<br><br>4:3<br><br>1:1<br><br>3:4<br><br>9:16 |21:9<br><br>16:9<br><br>4:3<br><br>1:1<br><br>3:4<br><br>9:16 |21:9<br><br>16:9<br><br>4:3<br><br>1:1<br><br>3:4<br><br>9:16 |21:9<br><br>16:9<br><br>4:3<br><br>1:1<br><br>3:4<br><br>9:16 |
| |输出帧率 |24 fps |24 fps |24 fps |24 fps |24 fps |24 fps |
| |输出时长<br><br>> "duration": 5 |4~15 秒 |4~15 秒 |4~15 秒 |4~12 秒 |2~12 秒 |2~12 秒 |
| |输出视频格式 |mp4 |mp4 |mp4 |mp4 |mp4 |mp4 |
|[离线推理](https://www.volcengine.com/docs/82379/2298881#c3588bd1)<br><br>> "service_tier": "flex" | |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/f359753773c94d97885008ca1223c9bc~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ee51ce32c1914aed81ff95080bb7db1d~tplv-goo7wpa0wc-image.image) </span> |
|在线推理限流 |最大 RPM |非 4k 分辨率：<br><br><br>* 企业用户：600<br><br>* 个人用户：180<br><br><br>4k 分辨率：<br><br><br>* 企业用户：15<br><br>* 个人用户：15 |* 企业用户：600<br><br>* 个人用户：180 |* 企业用户：600<br><br>* 个人用户：180 |600 |600 |600 |
| |最大并发数 |非 4k 分辨率：<br><br><br>* 企业用户：10<br><br>* 个人用户：3<br><br><br>4k 分辨率：<br><br><br>* 企业用户：1<br><br>* 个人用户：1 |* 企业用户：10<br><br>* 个人用户：3 |* 企业用户：10<br><br>* 个人用户：3 |10 |10 |10 |
|离线推理限流 |TPD |\- |\- |\- |5000亿 |5000亿 |5000亿 |


<span id="1bf58128"></span>
# 基础使用

<span id="4e74bcee"></span>
## 文生视频

根据用户输入的提示词生成视频，结果具有较大的随机性，可以用于激发创作灵感。


<span aceTableMode="list" aceTableWidth="1,1"></span>
|提示词 |输出 |
|---|---|
|写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/b847f3e831c244b39f7b4d53d904988f" controls></video><br> |



<Tabs>
<Tab zoneid="jB7Le3F1be" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark

# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID
        content=[
            {
                # Combination of text prompt and parameters
                "type": "text",
                "text": "写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠"
            }
        ],
        ratio="16:9",
        duration=5,
        watermark=True,
    )
    print(create_result)

    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)
```



</Tab>
<Tab zoneid="qYT5jtWmu9" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {
        String model = "doubao-seedance-2-0-260128"; // Replace with Model ID
        String ratio = "16:9";
        Long duration = 5L;
        Boolean watermark = false;
        System.out.println("----- create request -----");
        List<Content> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(Content.builder()
                .type("text")
                .text("写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠")
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);

        // Get the details of the task
        String taskId = createResult.getId();
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        // Polling query section
        System.out.println("----- polling task status -----");
        while (true) {
            try {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();
                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    System.out.println("Error: " + getResponse.getStatus());
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                System.err.println("Polling interrupted");
                break;
            }
        }
    }
}
```



</Tab>
<Tab zoneid="URj60pEBGu" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-2-0-260128"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        Ratio:         volcengine.String("16:9"),
        Duration:      volcengine.Int64(5),
        Watermark:     volcengine.Bool(false),
        Content: []*model.CreateContentGenerationContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String("写实风格，晴朗的蓝天之下，一大片白色的雏菊花田，镜头逐渐拉近，最终定格在一朵雏菊花的特写上，花瓣上有几颗晶莹的露珠"),
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)

    // Polling query section
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<span id="979b2d28"></span>
## 图生视频\-基于首帧（`含音频`）

通过指定视频的首帧图片，模型能够基于该图片生成与之相关且画面连贯的视频内容。

seedance 2.0 / seedance 1.5 pro 可通过设置参数 **generate_audio** 为 `true`，生成有声视频。


<span aceTableMode="list" aceTableWidth="3,4,4"></span>
|提示词 |首帧 |输出 |
|---|---|---|
|女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/a28ec84ff9fc4287a0d98191020a3218~tplv-goo7wpa0wc-image.image) </span> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/f1f7b95a38ee4ee094c724233e4da4f8" controls></video><br> |



<Tabs>
<Tab zoneid="NJkE6keqj5" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark

# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID
        content=[
            {
                # Combination of text prompt and parameters
                "type": "text",
                "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声"  
            },
            {
                # The URL of the first frame image
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"
                }
            }
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=5,
        watermark=True,
    )
    print(create_result)

    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)
```



</Tab>
<Tab zoneid="m3T1FA5j91" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {
        String model = "doubao-seedance-2-0-260128"; // Replace with Model ID
        Boolean generateAudio = true;
        String ratio = "adaptive";
        Long duration = 5L;
        Boolean watermark = false;
        System.out.println("----- create request -----");
        List<Content> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(Content.builder()
                .type("text")
                .text("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声")
                .build());
        // The URL of the first frame image
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url("https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png")
                        .build())
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .generateAudio(generateAudio)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);

        // Get the details of the task
        String taskId = createResult.getId();
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        // Polling query section
        System.out.println("----- polling task status -----");
        while (true) {
            try {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();
                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    System.out.println("Error: " + getResponse.getStatus());
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                System.err.println("Polling interrupted");
                break;
            }
        }
    }
}
```



</Tab>
<Tab zoneid="Z6C3MdbyjZ" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-2-0-260128"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        GenerateAudio: volcengine.Bool(true),
        Ratio:         volcengine.String("adaptive"),
        Duration:      volcengine.Int64(5),
        Watermark:     volcengine.Bool(false),
        Content: []*model.CreateContentGenerationContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声"),
            },
            {
                // The URL of the first frame image
                Type: model.ContentGenerationContentItemTypeImage,
                ImageURL: &model.ImageURL{
                    URL: "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png",
                },
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)

    // Polling query section
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<span id="0d55ca07"></span>
## 图生视频\-基于首尾帧（`含音频`）

通过指定视频的起始和结束图片，模型即可生成流畅衔接首、尾帧的视频，实现画面间自然、连贯的过渡效果。

seedance 2.0 / seedance 1.5 pro 可通过设置参数 **generate_audio** 为 `true`，生成有声视频。


<span aceTableMode="list" aceTableWidth="2,3,3,3"></span>
|提示词 |首帧 |尾帧 |输出 |
|---|---|---|---|
|图中女孩对着镜头说“茄子”，360度环绕运镜 |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/649cb2057eae48d6a6eec872d912c75c~tplv-goo7wpa0wc-image.image) </span> |<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/e39fd8e500a34bbdad50d06659c4ea6b~tplv-goo7wpa0wc-image.image) </span> |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/3aa8c84b8a29408ab29e95992d61c559" controls></video><br> |



<Tabs>
<Tab zoneid="d0ptW5yqY6" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark

# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)


if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID
        content=[
            {
                # Combination of text prompt and parameters
                "type": "text",
                "text": "图中女孩对着镜头说\"茄子\"，360度环绕运镜" 
            },
            {
                # The URL of the first frame image
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_first_frame.jpeg"
                },
                "role": "first_frame"
            },
            {
                # The URL of the last frame image
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_last_frame.jpeg"
                },
                "role": "last_frame"
            }
        ],
        generate_audio=True,
        ratio="adaptive",
        duration=5,
        watermark=True,
    )
    print(create_result)

    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)
```



</Tab>
<Tab zoneid="JpuaJN8kz6" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {
        String model = "doubao-seedance-2-0-260128"; // Replace with Model ID
        Boolean generateAudio = true;
        String ratio = "adaptive";
        Long duration = 5L;
        Boolean watermark = false;
        System.out.println("----- create request -----");
        List<Content> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(Content.builder()
                .type("text")
                .text("图中女孩对着镜头说“茄子”，360度环绕运镜")
                .build());
         // The URL of the first frame image
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url("https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_first_frame.jpeg")
                        .build())
                .role("first_frame")
                .build());

        // The URL of the last frame image
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url("https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_last_frame.jpeg")
                        .build())
                .role("last_frame")
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .generateAudio(generateAudio)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);

        // Get the details of the task
        String taskId = createResult.getId();
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        // Polling query section
        System.out.println("----- polling task status -----");
        while (true) {
            try {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();
                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    System.out.println("Error: " + getResponse.getStatus());
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 10 seconds...", status);
                    TimeUnit.SECONDS.sleep(10);
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                System.err.println("Polling interrupted");
                break;
            }
        }
    }
}
```



</Tab>
<Tab zoneid="B0zTuw3Bzu" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-2-0-260128"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        GenerateAudio: volcengine.Bool(true),
        Ratio:         volcengine.String("adaptive"),
        Duration:      volcengine.Int64(5),
        Watermark:     volcengine.Bool(false),
        Content: []*model.CreateContentGenerationContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String("图中女孩对着镜头说“茄子”，360度环绕运镜"),
            },
            {
                // The URL of the first frame image
                Type: model.ContentGenerationContentItemTypeImage,
                ImageURL: &model.ImageURL{
                    URL: "https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_first_frame.jpeg", 
                },
                Role: volcengine.String("first_frame"),
            },
            {
                // The URL of the last frame image
                Type: model.ContentGenerationContentItemTypeImage,
                ImageURL: &model.ImageURL{
                    URL: "https://ark-project.tos-cn-beijing.volces.com/doc_image/seepro_last_frame.jpeg", 
                },
                Role: volcengine.String("last_frame"),
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)

    // Polling query section
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
            time.Sleep(10 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


&nbsp;

<span id="68fd42bf"></span>
## 管理视频任务

<span id="360a1a86"></span>
### 查询视频生成任务列表

该接口支持传入条件筛选参数，以查询符合条件的视频生成任务列表。


<Tabs>
<Tab zoneid="Q2PXLZnWvt" title="Curl">
<TabTitle>Curl</TabTitle>

```Bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks?page_size=2&filter.status=succeeded& \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY"
```



</Tab>
<Tab zoneid="bMgg46YhJ1" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
from volcenginesdkarkruntime import Ark

client = Ark(api_key=os.environ.get("ARK_API_KEY"))

if __name__ == "__main__":
    resp = client.content_generation.tasks.get(
        task_id="cgt-2025****",
    )
    print(resp)
```



</Tab>
<Tab zoneid="Prqb35RzAi" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.volcengine.ark.runtime.model.content.generation.ListContentGenerationTasksRequest;
import com.volcengine.ark.runtime.service.ArkService;
import java.util.concurrent.TimeUnit;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;


public class Sample {

    static String apiKey = System.getenv("ARK_API_KEY");

    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service =
            ArkService.builder()
                    .dispatcher(dispatcher)
                    .connectionPool(connectionPool)
                    .apiKey(apiKey)
                    .build();

    public static void main(String[] args) throws JsonProcessingException {

        ListContentGenerationTasksRequest req =
                ListContentGenerationTasksRequest.builder().pageSize(3).status("succeeded").build();

        ListContentGenerationTasksResponse resp = service.listContentGenerationTasks(req);
        System.out.println(resp);

        // shutdown service after all requests is finished
        service.shutdownExecutor();
    }
}
```



</Tab>
<Tab zoneid="ENir1pwwXW" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
        client := arkruntime.NewClientWithApiKey(os.Getenv("ARK_API_KEY"))
        ctx := context.Background()

        req := model.ListContentGenerationTasksRequest{
                PageSize: volcengine.Int(3),
                Filter: &model.ListContentGenerationTasksFilter{
                        Status: volcengine.String("succeeded"),
                },
        }

        resp, err := client.ListContentGenerationTasks(ctx, req)
        if err != nil {
                fmt.Printf("failed to list content generation tasks: %v\n", err)
                return
        }
        fmt.Printf("%+v\n", resp)
}
```



</Tab>
</Tabs>


<span id="64914c89"></span>
### 删除或取消视频生成任务

取消排队中的视频生成任务，或者删除视频生成任务记录。


<Tabs>
<Tab zoneid="N0aHe0CbWg" title="Curl">
<TabTitle>Curl</TabTitle>

```Bash
# Replace cgt-2025**** with the ID acquired from "Create Video Generation Task".

curl -X DELETE https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-2025**** \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY"
```



</Tab>
<Tab zoneid="nbP3XLMFfE" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
from volcenginesdkarkruntime import Ark

client = Ark(api_key=os.environ.get("ARK_API_KEY"))

if __name__ == "__main__":
    try:
        client.content_generation.tasks.delete(
            task_id="cgt-2025****",
        )
    except Exception as e:
        print(f"failed to delete task: {e}")
```



</Tab>
<Tab zoneid="VXv865j6Ly" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.volcengine.ark.runtime.model.content.generation.DeleteContentGenerationTaskRequest;
import com.volcengine.ark.runtime.service.ArkService;
import java.util.concurrent.TimeUnit;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

public class Sample {

    static String apiKey = System.getenv("ARK_API_KEY");

    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service =
            ArkService.builder()
                    .dispatcher(dispatcher)
                    .connectionPool(connectionPool)
                    .apiKey(apiKey)
                    .build();

    public static void main(String[] args) throws JsonProcessingException {

        DeleteContentGenerationTaskRequest req =
                DeleteContentGenerationTaskRequest.builder()
                        .taskId("cgt-2025****")
                        .build();

        service.deleteContentGenerationTask(req).toString();

        service.shutdownExecutor();
    }
}
```



</Tab>
<Tab zoneid="kYw9jeiZet" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
        "context"
        "fmt"
        "os"

        "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
        "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
)


func main() {
        client := arkruntime.NewClientWithApiKey(os.Getenv("ARK_API_KEY"))
        ctx := context.Background()

        req := model.DeleteContentGenerationTaskRequest{
                ID: "cgt-2025****",
        }
        err := client.DeleteContentGenerationTask(ctx, req)
        if err != nil {
                fmt.Printf("delete content generation task error: %v\n", err)
                return
        }
}
```



</Tab>
</Tabs>


<span id="9fe4cce0"></span>
## 自定义视频输出规格

通过 API 参数控制输出视频的规格，包括分辨率、宽高比、时长、是否包含水印等。


<columns>
<columnsItem zoneid="dmvTfnHOvT">

**新方式（推荐）**  ：在 request body 中直接传入参数

> 此方式为强校验，若参数填写错误，模型会返回错误提示。


```JSON
...

   // Strongly recommended
   // Specify the aspect ratio of the generated video as 16:9, duration as 5 seconds, resolution as 720p, seed as 11, and include a watermark. The camera is not fixed.

    "content": [
         {
            "type": "text",
            "text": "<Your prompt>"
        }
    ],
    // All parameters must be written in full; abbreviations are not supported
    "resolution": "720p",
    "ratio":"16:9",
    "duration": 5,
    "seed": 11,
    "camera_fixed": false,
    "watermark": true

...

```


</columnsItem>
<columnsItem zoneid="y7MujDpLXx">

旧方式：在文本提示词后追加 \-\-[parameters]

> 此方式为弱校验，若参数填写错误，该参数将被忽略或触发报错。


```JSON
...

// Specify the aspect ratio of the generated video as 16:9, duration as 5 seconds, resolution as 720p, seed as 11, and include a watermark. The camera is not fixed.

"content": [
        {
            "type": "text",
            "text": "<Your prompt> --rs 720p --rt 16:9 --dur 5 --seed 11 --cf false --wm true"
            // "text": "<Your prompt> --resolution 720p --ratio 16:9 --duration 5 --seed 11 --camerafixed false --watermark true"
        }
    ]
 ...

```


</columnsItem>
</columns>


<span id="resolution"></span>
### 分辨率和宽高比

> 仅 Seedance 2.0 支持 4k

> Seedance 2.0 Fast、Seedance 2.0 Mini 不支持 1080p


通过以下参数控制输出视频的分辨率和宽高比，分辨率和宽高比将共同决定输出视频的像素尺寸。


* **resolution** ：指定输出视频的分辨率，支持 480p，720p，1080p，4k。

* **ratio** ：指定输出视频的宽高比，支持 16:9，4:3，1:1，3:4，9:16，21:9，adaptive。


```Json
{
    "resolution": "720p",
    "ratio":"16:9"
}
```


各模型输出视频的像素尺寸如下：


<span aceTableMode="table" aceTableWidth="2,2,3,3,3"></span>
|分辨率 |宽高比 |Seedance 2.0 系列 |Seedance 1.5 pro |Seedance 1.0 系列 |
|---|---|---|---|---|
|480p |16:9 |864×496 |864×496 |864×480 |
||4:3 |752×560 |752×560 |736×544 |
||1:1 |640×640 |640×640 |640×640 |
||3:4 |560×752 |560×752 |544×736 |
||9:16 |496×864 |496×864 |480×864 |
||21:9 |992×432 |992×432 |960×416 |
|720p |16:9 |1280×720 |1280×720 |1248×704 |
||4:3 |1112×834 |1112×834 |1120×832 |
||1:1 |960×960 |960×960 |960×960 |
||3:4 |834×1112 |834×1112 |832×1120 |
||9:16 |720×1280 |720×1280 |704×1248 |
||21:9 |1470×630 |1470×630 |1504×640 |
|1080p<br><br>> Seedance 2.0 Fast、Seedance 2.0 Mini 不支持 |16:9 |1920×1080 |1920×1080 |1920×1088 |
||4:3 |1664×1248 |1664×1248 |1664×1248 |
||1:1 |1440×1440 |1440×1440 |1440×1440 |
||3:4 |1248×1664 |1248×1664 |1248×1664 |
||9:16 |1080×1920 |1080×1920 |1088×1920 |
||21:9 |2206×946 |2206×946 |2176×928 |
|4k<br><br>> 仅 Seedance 2.0 支持 |16:9 |3840×2160 |— |— |
||4:3 |3326×2494 |— |— |
||1:1 |2880×2880 |— |— |
||3:4 |2494×3326 |— |— |
||9:16 |2160×3840 |— |— |
||21:9 |4398×1886 |— |— |


<span id="duration"></span>
### 视频时长

通过 **duration** 参数控制生成视频的时长（整数秒）：


* Seedance 1.0 系列: [2, 12]

* Seedance 1.5 pro: [4,12] 或设置为\-1

* Seedance 2.0 系列: [4,15] 或设置为\-1

> \-1 表示智能指定时长，由模型在有效范围内自主选择合适的视频长度（整数秒）


```Json
{
   "duration": 5
}
```


**Seedance 1.0 系列** 模型还支持通过 **frames** 参数指定生成视频的帧数，从而生成小数秒的视频。


* 计算公式：帧数 = 时长 × 帧率（24）。

* 取值范围：frames 支持 [29, 289] 区间内所有满足 25 + 4n 格式的整数值，其中 n 为正整数。

* 注意事项：duration 和 frames 二选一即可，frames 的优先级高于 duration。


```Json
{
   "frames": 29
}
```


<span id="watermark"></span>
### 视频中添加水印

通过 watermark 参数，来控制是否在生成的视频中添加水印。


* true：在视频右下角添加`AI生成`水印标识。

* false：不添加水印。


```Json
{
    "watermark": true
}
```


<span id="44236b6a"></span>
## 提示词建议


* **提示词 = 主体 + 运动， 背景 + 运动，镜头 + 运动 ...** 

* 用简洁准确的自然语言写出你想要的效果。

* 如果有较为明确的效果预期，建议先用生图模型生成符合预期的图片，再用图生视频进行视频片段的生成。

* 文生视频会有较大的结果随机性，可以用于激发创作灵感

* 图生视频时请尽量上传高清高质量的图片，上传图片的质量对图生视频影响较大。

* 当生成的视频不符合预期时，建议修改提示词，将抽象描述换成具象描述，并注意删除不重要的部分，将重要内容前置。

* 更多提示词的使用技巧请参见 [Seedance-1.5-pro 提示词指南](https://www.volcengine.com/docs/82379/2168087)、[Seedance-1.0-pro&pro-fast 提示词指南](https://www.volcengine.com/docs/82379/1631633)。


<span id="e190e738"></span>
# 进阶使用

<span id="c3588bd1"></span>
## 离线推理

> Seedance 2.0 系列不支持


针对推理时延敏感度低（例如小时级响应）的场景，建议将 **service_tier** 设为 `flex`，一键切换至离线推理模式——价格仅为在线推理的 50%，显著降低业务成本。

注意根据业务场景设置合适的超时时间，超过该时间后任务将自动终止。


<Tabs>
<Tab zoneid="U84Bfb8LvJ" title="Python">
<TabTitle>Python</TabTitle>

```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark

# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key: https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

if __name__ == "__main__":
    print("----- create request -----")
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-1-5-pro-251215", # Replace with Model ID
        content=[
            {
                # Combination of text prompt and parameters
                "type": "text",
                "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动"  
            },
            {
                # The URL of the first frame image
                "type": "image_url",
                "image_url": {
                    "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"
                }
            }
        ],
        ratio="adaptive",
        duration=5,
        watermark=False,
        service_tier="flex",
        execution_expires_after=172800,
    )
    print(create_result)

    # Polling query section
    print("----- polling task status -----")
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status
        if status == "succeeded":
            print("----- task succeeded -----")
            print(get_result)
            break
        elif status == "failed":
            print("----- task failed -----")
            print(f"Error: {get_result.error}")
            break
        else:
            print(f"Current status: {status}, Retrying after 60 seconds...")
            time.sleep(60)
```



</Tab>
<Tab zoneid="bHDR0J6dkR" title="Java">
<TabTitle>Java</TabTitle>

```Java
package com.ark.sample;

import com.volcengine.ark.runtime.model.content.generation.*;
import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
import com.volcengine.ark.runtime.service.ArkService;
import okhttp3.ConnectionPool;
import okhttp3.Dispatcher;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ContentGenerationTaskExample {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    static String apiKey = System.getenv("ARK_API_KEY");
    static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
    static Dispatcher dispatcher = new Dispatcher();
    static ArkService service = ArkService.builder()
           .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
           .dispatcher(dispatcher)
           .connectionPool(connectionPool)
           .apiKey(apiKey)
           .build();

    public static void main(String[] args) {
        String model = "doubao-seedance-1-5-pro-251215"; // Replace with Model ID
        String ratio = "adaptive";
        Long duration = 5L;
        Boolean watermark = false;
        String serviceTier = "flex";
        Long executionExpiresAfter = 172800L;
        System.out.println("----- create request -----");
        List<Content> contents = new ArrayList<>();

        // Combination of text prompt and parameters
        contents.add(Content.builder()
                .type("text")
                .text("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动")
                .build());
        // The URL of the first frame image
        contents.add(Content.builder()
                .type("image_url")
                .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                        .url("https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png")
                        .build())
                .build());

        // Create a video generation task
        CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                .model(model)
                .content(contents)
                .ratio(ratio)
                .duration(duration)
                .watermark(watermark)
                .serviceTier(serviceTier)
                .executionExpiresAfter(executionExpiresAfter)
                .build();

        CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
        System.out.println(createResult);

        // Get the details of the task
        String taskId = createResult.getId();
        GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                .taskId(taskId)
                .build();

        // Polling query section
        System.out.println("----- polling task status -----");
        while (true) {
            try {
                GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                String status = getResponse.getStatus();
                if ("succeeded".equalsIgnoreCase(status)) {
                    System.out.println("----- task succeeded -----");
                    System.out.println(getResponse);
                    break;
                } else if ("failed".equalsIgnoreCase(status)) {
                    System.out.println("----- task failed -----");
                    System.out.println("Error: " + getResponse.getStatus());
                    break;
                } else {
                    System.out.printf("Current status: %s, Retrying in 60 seconds...", status);
                    TimeUnit.SECONDS.sleep(60);
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                System.err.println("Polling interrupted");
                break;
            }
        }
    }
}
```



</Tab>
<Tab zoneid="Fe2fHSX0ww" title="Go">
<TabTitle>Go</TabTitle>

```Go
package main

import (
    "context"
    "fmt"
    "os"
    "time"

    "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
    "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
    "github.com/volcengine/volcengine-go-sdk/volcengine"
)

func main() {
    // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
    // Initialize the Ark client to read your API Key from an environment variable
    client := arkruntime.NewClientWithApiKey(
        // Get your API Key from the environment variable. This is the default mode and you can modify it as required
        os.Getenv("ARK_API_KEY"),
        // The base URL for model invocation
        arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
    )
    ctx := context.Background()
    // Replace with Model ID
    modelEp := "doubao-seedance-1-5-pro-251215"

    // Generate a task
    fmt.Println("----- create request -----")
    createReq := model.CreateContentGenerationTaskRequest{
        Model: modelEp,
        Ratio:                 volcengine.String("adaptive"),
        Duration:              volcengine.Int64(5),
        Watermark:             volcengine.Bool(false),
        ServiceTier:           volcengine.String("flex"),
        ExecutionExpiresAfter: volcengine.Int64(172800),
        Content: []*model.CreateContentGenerationContentItem{
            {
                // Combination of text prompt and parameters
                Type: model.ContentGenerationContentItemTypeText,
                Text: volcengine.String("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动"),
            },
            {
                // The URL of the first frame image
                Type: model.ContentGenerationContentItemTypeImage,
                ImageURL: &model.ImageURL{
                    URL: "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png",
                },
            },
        },
    }
    createResp, err := client.CreateContentGenerationTask(ctx, createReq)
    if err != nil {
        fmt.Printf("create content generation error: %v", err)
        return
    }
    taskID := createResp.ID
    fmt.Printf("Task Created with ID: %s", taskID)

    // Polling query section
    fmt.Println("----- polling task status -----")
    for {
        getReq := model.GetContentGenerationTaskRequest{ID: taskID}
        getResp, err := client.GetContentGenerationTask(ctx, getReq)
        if err != nil {
            fmt.Printf("get content generation task error: %v", err)
            return
        }

        status := getResp.Status
        if status == "succeeded" {
            fmt.Println("----- task succeeded -----")
            fmt.Printf("Task ID: %s \n", getResp.ID)
            fmt.Printf("Model: %s \n", getResp.Model)
            fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
            fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
            fmt.Printf("Created At: %d, Updated At: %d", getResp.CreatedAt, getResp.UpdatedAt)
            return
        } else if status == "failed" {
            fmt.Println("----- task failed -----")
            if getResp.Error != nil {
                fmt.Printf("Error Code: %s, Message: %s", getResp.Error.Code, getResp.Error.Message)
            }
            return
        } else {
            fmt.Printf("Current status: %s, Retrying in 60 seconds... \n", status)
            time.Sleep(60 * time.Second)
        }
    }
}
```



</Tab>
</Tabs>


<span id="5acd28c8"></span>
## 样片模式

> 仅支持 seedance 1.5 pro


获得一个符合预期的生产级别视频，通常需要多次抽卡，耗时耗力。样片模式是平台推出的中间产物可视化功能，开启该功能后，将生成一段预览视频，帮助用户 **低成本验证** 生成视频的场景结构、镜头调度、主体动作与 Prompt 意图等关键要素是否符合预期，快速调整方向。确认符合预期后，再基于 Draft 视频生成最终的高质量视频。


<span aceTableMode="list" aceTableWidth="3,3,3"></span>
|输入 |Draft 视频 |正式视频 |
|---|---|---|
|<span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/ebb5217645b04cfc94209a6f7d36a523~tplv-goo7wpa0wc-image.image) </span><br><br>> 提示词：女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动，可以听到风声 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/7c190b3a0ed34b29bc1192acbce2f4d2" controls></video><br><br><br>> 生成一段预览视频，低成本验证结果。 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/a82cd582a5d54f34a8adec10f2815081" controls></video><br><br><br>> 复用 Draft 视频使用 **模型、提示词、输入图片、种子值、音频设置、视频宽高比、视频时长等** 生成正式视频，保证视频关键要素一致。 |


本功能使用分为两步：

<span id="13ae3900"></span>
### Step1: 生成 Draft 视频


1. 设置 `"draft": true`，调用`POST /contents/generations/tasks`接口创建 Draft 视频生成任务。

2. 调用`GET /contents/generations/tasks/{id}`接口查询生成状态和结果，下载 Draft 视频，确认是否符合预期。


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip">仅 seedance 1.5 pro 支持该功能。</div>


* <div data-tips="true" data-tips-type="tip">仅支持 480p 分辨率（使用其他分辨率会报错），不支持返回尾帧功能，不支持离线推理功能。</div>


* <div data-tips="true" data-tips-type="tip">Draft 视频的 token 单价不变，消耗的 token 更少。<code>Draft视频token用量 = 正常视频token用量 × 折算系数</code>，以 seedance 1.5 pro 为例，有声视频的折算系数为 0.6，故生成一个 Draft 有声视频的价格是正常视频的 0.6 倍，显著降低了成本。</div>




<Tabs>
<Tab zoneid="Y6VnOQ4Uhq" title="Curl">
<TabTitle>Curl</TabTitle>

1. 创建 Draft 视频生成任务。


```Bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-1-5-pro-251215",
    "content": [
        {
            "type": "text",
            "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"
            }
        }
    ],
    "seed": 20,
    "duration": 6,
    "draft": true
}'
```


请求成功后，系统将返回一个任务 ID。此 ID 即为 Draft 视频任务 ID，后续需基于这个 ID 生成最终视频。


2. 使用 Draft 视频任务 ID，查询生成状态和结果

   ```Bash
   # Replace cgt-2026****-pzjqb with the ID acquired from last step
   
   curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-2026****-pzjqb \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $ARK_API_KEY"
   ```
   


当任务状态变为 succeeded 后，您可在 content.**video_url** 字段处，下载生成的 Draft 视频文件，检视效果是否符合预期。若不符合预期，可重新调整参数并再次创建 Draft 视频生成任务。当确认 Draft 视频效果符合预期后，即可按照后续步骤生成最终视频。


</Tab>
<Tab zoneid="bv7aqsgILf" title="Python">
<TabTitle>Python</TabTitle>

1. 创建 Draft 视频任务并轮询任务状态；

2. 当任务状态变为 `succeeded`后，您可在 content.**video_url** 字段处，下载生成的 Draft 视频文件，检视效果是否符合预期。若不符合预期，可重新调整参数并再次创建 Draft 视频生成任务。当确认 Draft 视频效果符合预期后，即可按照后续步骤生成最终视频。

   ```Python
   import os
   import time
   # Install SDK:  pip install 'volcengine-python-sdk[ark]'
   from volcenginesdkarkruntime import Ark
   
   # Make sure that you have stored the API Key in the environment variable ARK_API_KEY
   # Initialize the Ark client to read your API Key from an environment variable
   client = Ark(
       # This is the default path. You can configure it based on the service location
       base_url="https://ark.cn-beijing.volces.com/api/v3",
       # Get API Key: https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
       api_key=os.environ.get("ARK_API_KEY"),
   )
   
   if __name__ == "__main__":
       print("----- create request -----")
       create_result = client.content_generation.tasks.create(
           model="doubao-seedance-1-5-pro-251215", # Replace with Model ID
           content=[
               {
                   # Combination of text prompt and parameters
                   "type": "text",
                   "text": "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动"
               },
               {
                   # The URL of the first frame image
                   "type": "image_url",
                   "image_url": {
                       "url": "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"
                   }
               }
           ],
           seed= 20,
           duration= 6,
           draft= True,
       )
       print(create_result)
   
       # Polling query section
       print("----- polling task status -----")
       task_id = create_result.id
       while True:
           get_result = client.content_generation.tasks.get(task_id=task_id)
           status = get_result.status
           if status == "succeeded":
               print("----- task succeeded -----")
               print(get_result)
               break
           elif status == "failed":
               print("----- task failed -----")
               print(f"Error: {get_result.error}")
               break
           else:
               print(f"Current status: {status}, Retrying after 10 seconds...")
               time.sleep(10)
   ```
   


</Tab>
<Tab zoneid="rH0qXZtaqb" title="Java">
<TabTitle>Java</TabTitle>

1. 创建 Draft 视频任务并轮询任务状态；

2. 当任务状态变为 `succeeded`后，您可在 content.**video_url** 字段处，下载生成的 Draft 视频文件，检视效果是否符合预期。若不符合预期，可重新调整参数并再次创建 Draft 视频生成任务。当确认 Draft 视频效果符合预期后，即可按照后续步骤生成最终视频。

   ```Java
   package com.ark.sample;
   
   import com.volcengine.ark.runtime.model.content.generation.*;
   import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
   import com.volcengine.ark.runtime.service.ArkService;
   import okhttp3.ConnectionPool;
   import okhttp3.Dispatcher;
   
   import java.util.ArrayList;
   import java.util.List;
   import java.util.concurrent.TimeUnit;
   
   public class ContentGenerationTaskExample {
       // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
       // Initialize the Ark client to read your API Key from an environment variable
       static String apiKey = System.getenv("ARK_API_KEY");
       static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
       static Dispatcher dispatcher = new Dispatcher();
       static ArkService service = ArkService.builder()
              .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
              .dispatcher(dispatcher)
              .connectionPool(connectionPool)
              .apiKey(apiKey)
              .build();
   
       public static void main(String[] args) {
           String model = "doubao-seedance-1-5-pro-251215"; // Replace with Model ID
           Long seed = 20L;
           Long duration = 6L;
           Boolean draft = true;
           System.out.println("----- create request -----");
           List<Content> contents = new ArrayList<>();
   
           // Combination of text prompt and parameters
           contents.add(Content.builder()
                   .type("text")
                   .text("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动")
                   .build());
           // The URL of the first frame image
           contents.add(Content.builder()
                   .type("image_url")
                   .imageUrl(CreateContentGenerationTaskRequest.ImageUrl.builder()
                           .url("https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png")
                           .build())
                   .build());
   
           // Create a video generation task
           CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                   .model(model)
                   .content(contents)
                   .seed(seed)
                   .duration(duration)
                   .draft(draft)
                   .build();
   
           CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
           System.out.println(createResult);
   
           // Get the details of the task
           String taskId = createResult.getId();
           GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                   .taskId(taskId)
                   .build();
   
           // Polling query section
           System.out.println("----- polling task status -----");
           while (true) {
               try {
                   GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                   String status = getResponse.getStatus();
                   if ("succeeded".equalsIgnoreCase(status)) {
                       System.out.println("----- task succeeded -----");
                       System.out.println(getResponse);
                       break;
                   } else if ("failed".equalsIgnoreCase(status)) {
                       System.out.println("----- task failed -----");
                       System.out.println("Error: " + getResponse.getStatus());
                       break;
                   } else {
                       System.out.printf("Current status: %s, Retrying in 10 seconds...", status);
                       TimeUnit.SECONDS.sleep(10);
                   }
               } catch (InterruptedException ie) {
                   Thread.currentThread().interrupt();
                   System.err.println("Polling interrupted");
                   break;
               }
           }
       }
   }
   ```
   


</Tab>
<Tab zoneid="wIUM662Wco" title="Go">
<TabTitle>Go</TabTitle>

1. 创建 Draft 视频任务并轮询任务状态；

2. 当任务状态变为 `succeeded`后，您可在 content.**video_url** 字段处，下载生成的 Draft 视频文件，检视效果是否符合预期。若不符合预期，可重新调整参数并再次创建 Draft 视频生成任务。当确认 Draft 视频效果符合预期后，即可按照后续步骤生成最终视频。

   ```Go
   package main
   
   import (
       "context"
       "fmt"
       "time"
       "os"
   
       "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
       "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
       "github.com/volcengine/volcengine-go-sdk/volcengine"
   )
   
   func main() {
       // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
       // Initialize the Ark client to read your API Key from an environment variable
       client := arkruntime.NewClientWithApiKey(
           // Get your API Key from the environment variable. This is the default mode and you can modify it as required
           os.Getenv("ARK_API_KEY"),
           // The base URL for model invocation
           arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
       )
       ctx := context.Background()
       // Replace with Model ID
       modelEp := "doubao-seedance-1-5-pro-251215"
   
       // Generate a task
       fmt.Println("----- create request -----")
       createReq := model.CreateContentGenerationTaskRequest{
           Model: modelEp,
           Seed:          volcengine.Int64(20),
           Duration:      volcengine.Int64(6),
           Draft:         volcengine.Bool(true),
           Content: []*model.CreateContentGenerationContentItem{
               {
                   // Combination of text prompt and parameters
                   Type: model.ContentGenerationContentItemTypeText,
                   Text: volcengine.String("女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动"),
               },
               {
                   // The URL of the first frame image
                   Type: model.ContentGenerationContentItemTypeImage,
                   ImageURL: &model.ImageURL{
                       URL: "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png",
                   },
               },
           },
       }
       createResp, err := client.CreateContentGenerationTask(ctx, createReq)
       if err != nil {
           fmt.Printf("create content generation error: %v", err)
           return
       }
       taskID := createResp.ID
       fmt.Printf("Task Created with ID: %s", taskID)
   
       // Polling query section
       fmt.Println("----- polling task status -----")
       for {
           getReq := model.GetContentGenerationTaskRequest{ID: taskID}
           getResp, err := client.GetContentGenerationTask(ctx, getReq)
           if err != nil {
               fmt.Printf("get content generation task error: %v", err)
               return
           }
   
           status := getResp.Status
           if status == "succeeded" {
               fmt.Println("----- task succeeded -----")
               fmt.Printf("Task ID: %s \n", getResp.ID)
               fmt.Printf("Model: %s \n", getResp.Model)
               fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
               fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
               fmt.Printf("Created At: %d, Updated At: %d", getResp.CreatedAt, getResp.UpdatedAt)
               return
           } else if status == "failed" {
               fmt.Println("----- task failed -----")
               if getResp.Error != nil {
                   fmt.Printf("Error Code: %s, Message: %s", getResp.Error.Code, getResp.Error.Message)
               }
               return
           } else {
               fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
               time.Sleep(10 * time.Second)
           }
       }
   }
   ```
   


</Tab>
</Tabs>


<span id="015173ef"></span>
### Step2: 基于 Draft 视频生成正式视频

如果确认 Draft 视频符合预期，可基于 Step1 返回的 Draft 视频任务 ID，再次调用`POST /contents/generations/tasks`接口，生成最终视频。

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip">平台将自动复用 Draft 视频使用的用户输入（ <strong>model、</strong> content. <strong>text、</strong> content. <strong>image_url、generate_audio、seed、ratio、duration、</strong> <strong>camera_fixed</strong> ），生成正式视频。</div>


* <div data-tips="true" data-tips-type="tip">其余参数支持指定，不指定将使用本模型的默认值。例如：指定正式视频的分辨率、是否包含水印、是否使用离线推理、是否返回尾帧等。</div>


* <div data-tips="true" data-tips-type="tip">基于 Draft 视频生成最终视频属于正常推理过程，按照正常视频消耗 token 量计费。</div>


* <div data-tips="true" data-tips-type="tip">Draft 视频任务 ID 的有效期为 7 天（从 <strong>created at</strong> 时间戳开始计算），超时后将无法使用该 Draft 视频生成正式视频。</div>




<Tabs>
<Tab zoneid="wOScRDBZLn" title="Curl">
<TabTitle>Curl</TabTitle>

1. 基于 `content.draft_task.id` 创建视频生成任务。


```Bash
curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "doubao-seedance-1-5-pro-251215",
    "content": [
        {
            "type": "draft_task",
            "draft_task": {"id": "cgt-2026****-pzjqb"}
        }
    ],
      "watermark": false,
      "resolution": "720p",
      "return_last_frame": true,
      "service_tier": "default"
  }'
```


请求成功后，系统将返回一个任务 ID。


2. 使用视频任务 ID，查询生成状态和结果

   ```Bash
   # Replace cgt-2026****-bn6zj with the ID acquired from last step
   
   curl https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/cgt-2026****-bn6zj \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $ARK_API_KEY"
   ```
   


当任务状态变为 succeeded 后，您可在 content.**video_url** 字段处，下载生成的视频文件。


</Tab>
<Tab zoneid="XMIz5Uqq3A" title="Python">
<TabTitle>Python</TabTitle>

1. 基于`content.draft_task.id` (此 ID 通过 Step1 的返回信息获取）创建视频生成任务并轮询获取任务状态；

2. 当任务状态变为 `succeeded` 后，您可在 content.**video_url** 字段处，下载生成的视频文件。

   ```Python
   import os
   import time
   # Install SDK:  pip install 'volcengine-python-sdk[ark]'
   from volcenginesdkarkruntime import Ark
   
   # Make sure that you have stored the API Key in the environment variable ARK_API_KEY
   # Initialize the Ark client to read your API Key from an environment variable
   client = Ark(
       # This is the default path. You can configure it based on the service location
       base_url="https://ark.cn-beijing.volces.com/api/v3",
       # Get API Key: https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
       api_key=os.environ.get("ARK_API_KEY"),
   )
   
   if __name__ == "__main__":
       print("----- create request -----")
       create_result = client.content_generation.tasks.create(
           model="doubao-seedance-1-5-pro-251215", # Replace with Model ID
           content=[
               {
                   "type": "draft_task",
                   "draft_task": {
                       "id": "cgt-2026****-pzjqb"
                   }
               }
           ],
           watermark= False,
           resolution= "720p",
           return_last_frame= True,
           service_tier= "default",
       )
       print(create_result)
   
       # Polling query section
       print("----- polling task status -----")
       task_id = create_result.id
       while True:
           get_result = client.content_generation.tasks.get(task_id=task_id)
           status = get_result.status
           if status == "succeeded":
               print("----- task succeeded -----")
               print(get_result)
               break
           elif status == "failed":
               print("----- task failed -----")
               print(f"Error: {get_result.error}")
               break
           else:
               print(f"Current status: {status}, Retrying after 10 seconds...")
               time.sleep(10)
   ```
   


</Tab>
<Tab zoneid="KRaSv7lj5N" title="Java">
<TabTitle>Java</TabTitle>

1. 基于`content.draft_task.id` (此 ID 通过 Step1 的返回信息获取）创建视频生成任务并轮询获取任务状态；

2. 当任务状态变为 `succeeded` 后，您可在 content.**video_url** 字段处，下载生成的视频文件。

   ```Java
   package com.ark.sample;
   
   import com.volcengine.ark.runtime.model.content.generation.*;
   import com.volcengine.ark.runtime.model.content.generation.CreateContentGenerationTaskRequest.Content;
   import com.volcengine.ark.runtime.service.ArkService;
   import okhttp3.ConnectionPool;
   import okhttp3.Dispatcher;
   
   import java.util.ArrayList;
   import java.util.List;
   import java.util.concurrent.TimeUnit;
   
   public class ContentGenerationTaskExample {
       // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
       // Initialize the Ark client to read your API Key from an environment variable
       static String apiKey = System.getenv("ARK_API_KEY");
       static ConnectionPool connectionPool = new ConnectionPool(5, 1, TimeUnit.SECONDS);
       static Dispatcher dispatcher = new Dispatcher();
       static ArkService service = ArkService.builder()
              .baseUrl("https://ark.cn-beijing.volces.com/api/v3") // The base URL for model invocation
              .dispatcher(dispatcher)
              .connectionPool(connectionPool)
              .apiKey(apiKey)
              .build();
   
       public static void main(String[] args) {
           String model = "doubao-seedance-1-5-pro-251215"; // Replace with Model ID
           Boolean watermark = false;
           String resolution = "720p";
           Boolean returnLastFrame = true;
           String serviceTier = "default";
           System.out.println("----- create request -----");
           List<Content> contents = new ArrayList<>();
   
           // Combination of text prompt and parameters
           contents.add(Content.builder()
                   .type("draft_task")
                   .draftTask(CreateContentGenerationTaskRequest.DraftTask.builder()
                           .id("cgt-2026****-pzjqb")
                           .build())
                    .build());
   
   
           // Create a video generation task
           CreateContentGenerationTaskRequest createRequest = CreateContentGenerationTaskRequest.builder()
                   .model(model)
                   .content(contents)
                   .watermark(watermark)
                   .resolution(resolution)
                   .returnLastFrame(returnLastFrame)
                   .serviceTier(serviceTier)
                   .build();
   
           CreateContentGenerationTaskResult createResult = service.createContentGenerationTask(createRequest);
           System.out.println(createResult);
   
           // Get the details of the task
           String taskId = createResult.getId();
           GetContentGenerationTaskRequest getRequest = GetContentGenerationTaskRequest.builder()
                   .taskId(taskId)
                   .build();
   
           // Polling query section
           System.out.println("----- polling task status -----");
           while (true) {
               try {
                   GetContentGenerationTaskResponse getResponse = service.getContentGenerationTask(getRequest);
                   String status = getResponse.getStatus();
                   if ("succeeded".equalsIgnoreCase(status)) {
                       System.out.println("----- task succeeded -----");
                       System.out.println(getResponse);
                       break;
                   } else if ("failed".equalsIgnoreCase(status)) {
                       System.out.println("----- task failed -----");
                       System.out.println("Error: " + getResponse.getStatus());
                       break;
                   } else {
                       System.out.printf("Current status: %s, Retrying in 10 seconds...", status);
                       TimeUnit.SECONDS.sleep(10);
                   }
               } catch (InterruptedException ie) {
                   Thread.currentThread().interrupt();
                   System.err.println("Polling interrupted");
                   break;
               }
           }
       }
   }
   ```
   


</Tab>
<Tab zoneid="OcKFlEjaGe" title="Go">
<TabTitle>Go</TabTitle>

1. 基于`content.draft_task.id` (此 ID 通过 Step1 的返回信息获取）创建视频生成任务并轮询获取任务状态；

2. 当任务状态变为 `succeeded` 后，您可在 content.**video_url** 字段处，下载生成的视频文件。

   ```Go
   package main
   
   import (
       "context"
       "fmt"
       "time"
       "os"
   
       "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
       "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
       "github.com/volcengine/volcengine-go-sdk/volcengine"
   )
   
   func main() {
       // Make sure that you have stored the API Key in the environment variable ARK_API_KEY
       // Initialize the Ark client to read your API Key from an environment variable
       client := arkruntime.NewClientWithApiKey(
           // Get your API Key from the environment variable. This is the default mode and you can modify it as required
           os.Getenv("ARK_API_KEY"),
           // The base URL for model invocation
           arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),
       )
       ctx := context.Background()
       // Replace with Model ID
       modelEp := "doubao-seedance-1-5-pro-251215"
   
       // Generate a task
       fmt.Println("----- create request -----")
       createReq := model.CreateContentGenerationTaskRequest{
           Model: modelEp,
            Watermark:         volcengine.Bool(false),
            Resolution:        volcengine.String("720p"),
            ReturnLastFrame:   volcengine.Bool(true),
            ServiceTier:       volcengine.String("default"),
           Content: []*model.CreateContentGenerationContentItem{
               {
                   Type:      model.ContentGenerationContentItemTypeDraftTask,
                   DraftTask: &model.DraftTask{ID: "cgt-2026****-pzjqb"},
               },
           },
       }
   
       createResp, err := client.CreateContentGenerationTask(ctx, createReq)
       if err != nil {
           fmt.Printf("create content generation error: %v", err)
           return
       }
       taskID := createResp.ID
       fmt.Printf("Task Created with ID: %s", taskID)
   
       // Polling query section
       fmt.Println("----- polling task status -----")
       for {
           getReq := model.GetContentGenerationTaskRequest{ID: taskID}
           getResp, err := client.GetContentGenerationTask(ctx, getReq)
           if err != nil {
               fmt.Printf("get content generation task error: %v", err)
               return
           }
   
           status := getResp.Status
           if status == "succeeded" {
               fmt.Println("----- task succeeded -----")
               fmt.Printf("Task ID: %s \n", getResp.ID)
               fmt.Printf("Model: %s \n", getResp.Model)
               fmt.Printf("Video URL: %s \n", getResp.Content.VideoURL)
               fmt.Printf("Completion Tokens: %d \n", getResp.Usage.CompletionTokens)
               fmt.Printf("Created At: %d, Updated At: %d", getResp.CreatedAt, getResp.UpdatedAt)
               return
           } else if status == "failed" {
               fmt.Println("----- task failed -----")
               if getResp.Error != nil {
                   fmt.Printf("Error Code: %s, Message: %s", getResp.Error.Code, getResp.Error.Message)
               }
               return
           } else {
               fmt.Printf("Current status: %s, Retrying in 10 seconds... \n", status)
               time.Sleep(10 * time.Second)
           }
       }
   }
   ```
   


</Tab>
</Tabs>


<span id="141cf7fa"></span>
## 生成多个连续视频

使用前一个生成视频的尾帧，作为后一个视频任务的首帧，循环生成多个连续的视频。

后续您可以自行使用 FFmpeg 等工具，将生成的多个短视频拼接成一个完整长视频。


<span aceTableMode="list" aceTableWidth="1,1,1"></span>
|输出1 |输出2 |输出3 |
|---|---|---|
|<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/c984894e448f43ca8a593babe411a078" controls></video><br><br><br>> 女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动<br><br>> A girl holding a fox, the girl opens her eyes, looks gently at the camera, the fox hugs affectionately, the camera slowly pulls out, the girl's hair is blown by the wind |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/ccb8cebc70bd42738ba8d4bb894b69e6" controls></video><br><br><br>> 女孩和狐狸在草地上奔跑，阳光明媚，女孩的笑容灿烂，狐狸欢快地跳跃<br><br>> A girl and a fox running on the grass, sunny weather, the girl's smile is brilliant, the fox jumps happily |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/b78ed8dd418a4c97ac94253cb0c00728" controls></video><br><br><br>> 女孩和狐狸坐在树下休息，女孩轻轻抚摸狐狸的毛发，狐狸温顺地趴在女孩腿上<br><br>> A girl and a fox resting under a tree, the girl gently strokes the fox's fur, the fox lies meekly on the girl's lap |


```Python
import os
import time
# Install SDK:  pip install 'volcengine-python-sdk[ark]'
from volcenginesdkarkruntime import Ark

# Make sure that you have stored the API Key in the environment variable ARK_API_KEY
# Initialize the Ark client to read your API Key from an environment variable
client = Ark(
    # This is the default path. You can configure it based on the service location
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # Get API Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apikey
    api_key=os.environ.get("ARK_API_KEY"),
)

def generate_video_with_last_frame(prompt, initial_image_url=None):
    """
    Generate video and return video URL and last frame URL
    Parameters:
    prompt: Text prompt for video generation
    initial_image_url: Initial image URL (optional)
    Returns:
    video_url: Generated video URL
    last_frame_url: URL of the last frame of the video
    """
    print(f"----- Generating video: {prompt} -----")

    # Build content list
    content = [{
        "text": prompt,
        "type": "text"
    }]

    # If initial image is provided, add to content
    if initial_image_url:
        content.append({
            "image_url": {
                "url": initial_image_url
            },
            "type": "image_url"
        })

    # Create video generation task
    create_result = client.content_generation.tasks.create(
        model="doubao-seedance-2-0-260128", # Replace with Model ID
        content=content,
        return_last_frame=True,
        ratio="adaptive",
        duration=5,
        watermark=False,
    )

    # Poll to check task status
    task_id = create_result.id
    while True:
        get_result = client.content_generation.tasks.get(task_id=task_id)
        status = get_result.status

        if get_result.status == "succeeded":
            print("Video generation succeeded")
            try:
                if hasattr(get_result, 'content') and hasattr(get_result.content, 'video_url') and hasattr(get_result.content, 'last_frame_url'):
                    return get_result.content.video_url, get_result.content.last_frame_url
                print("Failed to obtain video URL or last frame URL")
                return None, None
            except Exception as e:
                print(f"Error occurred while obtaining video URL and last frame URL: {e}")
                return None, None
        elif status == "failed":
            print(f"----- Video generation failed -----")
            print(f"Error: {get_result.error}")
            return None, None
        else:
            print(f"Current status: {status}, retrying in 10 seconds...")
            time.sleep(10)



if __name__ == "__main__":
    # Define 3 video prompts
    prompts = [
        "女孩抱着狐狸，女孩睁开眼，温柔地看向镜头，狐狸友善地抱着，镜头缓缓拉出，女孩的头发被风吹动",
        "女孩和狐狸在草地上奔跑，阳光明媚，女孩的笑容灿烂，狐狸欢快地跳跃",
        "女孩和狐狸坐在树下休息，女孩轻轻抚摸狐狸的毛发，狐狸温顺地趴在女孩腿上"
    ]

    # Store generated video URLs
    video_urls = []

    # Initial image URL
    initial_image_url = "https://ark-project.tos-cn-beijing.volces.com/doc_image/i2v_foxrgirl.png"

    # Generate 3 short videos
    for i, prompt in enumerate(prompts):
        print(f"Generating video {i+1}")
        video_url, last_frame_url = generate_video_with_last_frame(prompt, initial_image_url)

        if video_url and last_frame_url:
            video_urls.append(video_url)
            print(f"Video {i+1} URL: {video_url}")
            # Use the last frame of the current video as the first frame of the next video
            initial_image_url = last_frame_url
        else:
            print(f"Video {i+1} generation failed, exiting program")
            exit(1)

    print("All videos generated successfully!")
    print("Generated video URL list:")
    for i, url in enumerate(video_urls):
        print(f"Video {i+1}: {url}")
```


<span id="caf01f12"></span>
## 使用 Webhook 通知

通过 **callback_url** 参数可以指定一个回调通知地址，当视频生成任务的状态发生变化时，方舟会向该地址发送一条 POST 请求，方便您及时获取任务最新情况。 请求内容结构与 [查询任务API](https://www.volcengine.com/docs/82379/1521309) 的返回体一致。

```Bash
{
  "id": "cgt-2025****",
  "model": "doubao-seedance-2-0-260128",
  "status": "running", # Possible status values: queued, running, succeeded, failed, expired
  "created_at": 1765434920,
  "updated_at": 1765434920,
  "service_tier": "default",
  "execution_expires_after": 172800
}
```


您需要自行搭建一个公网可访问的 Web Server 来接收 Webhook 通知。以下是一个简单的 Web Server 代码示例，供您参考。

```Python
# Building a Simple Web Server with Python Flask for Webhook Notification Processing

from flask import Flask, request, jsonify
import sqlite3
import logging
from datetime import datetime
import os

# === Basic Configuration ===
app = Flask(__name__)
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('webhook.log'), logging.StreamHandler()]
)
# Database path
DB_PATH = 'video_tasks.db'

# === Database Initialization ===
def init_db():
    """Automatically create task table on first run, aligning fields with callback parameters"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Create table: task_id as primary key for idempotent updates
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_generation_tasks (
        task_id TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        service_tier TEXT NOT NULL,
        execution_expires_after INTEGER NOT NULL,
        last_callback_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized, table created/exists")

# === Core Webhook Interface ===
@app.route('/webhook/callback', methods=['POST'])
def video_task_callback():
    """Core interface for receiving Ark callback"""
    try:
        # 1. Parse callback request body (JSON format)
        callback_data = request.get_json()
        if not callback_data:
            logging.error("Callback request body empty or non-JSON format")
            return jsonify({"code": 400, "msg": "Invalid JSON data"}), 400

        # 2. Validate required fields
        required_fields = ['id', 'model', 'status', 'created_at', 'updated_at', 'service_tier', 'execution_expires_after']
        for field in required_fields:
            if field not in callback_data:
                logging.error(f"Callback data missing required field: {field}, data: {callback_data}")
                return jsonify({"code": 400, "msg": f"Missing field: {field}"}), 400

        # 3. Extract key information and log
        task_id = callback_data['id']
        status = callback_data['status']
        model = callback_data['model']
        logging.info(f"Received task callback | Task ID: {task_id} | Status: {status} | Model: {model}")
        print(f"[{datetime.now()}] Task {task_id} status updated to: {status}")  # Console output

        # 4. Database operation
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT OR REPLACE INTO video_generation_tasks (
            task_id, model, status, created_at, updated_at, service_tier, execution_expires_after
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_id,
            model,
            status,
            callback_data['created_at'],
            callback_data['updated_at'],
            callback_data['service_tier'],
            callback_data['execution_expires_after']
        ))
        conn.commit()
        conn.close()
        logging.info(f"Task {task_id} database update successful")

        # 5. Return 200 response
        return jsonify({"code": 200, "msg": "Callback received successfully", "task_id": task_id}), 200

    except Exception as e:
        # Catch all exceptions to avoid returning 5xx
        logging.error(f"Callback processing failed: {str(e)}", exc_info=True)
        return jsonify({"code": 200, "msg": "Callback received successfully (internal processing exception)"}), 200

# === Helper Interface (Optional, for querying task status) ===
@app.route('/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Query latest status of specified task"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM video_generation_tasks WHERE task_id = ?', (task_id,))
    task = cursor.fetchone()
    conn.close()
    if not task:
        return jsonify({"code": 404, "msg": "Task not found"}), 404
    # Map field names for response
    fields = ['task_id', 'model', 'status', 'created_at', 'updated_at', 'service_tier', 'execution_expires_after', 'last_callback_at']
    task_dict = dict(zip(fields, task))
    return jsonify({"code": 200, "data": task_dict}), 200

# === Service Startup ===
if __name__ == '__main__':
    # Initialize database
    init_db()
    # Start Flask service (bind to 0.0.0.0 for public access, port customizable)
    # Test environment: debug=True; Production environment should disable debug and use gunicorn
    app.run(host='0.0.0.0', port=8080, debug=False)
```


<span id="66cb028f"></span>
# 使用限制

<span id="63a97f09"></span>
## 多模态输入

<div data-tips="true" data-tips-type="warning" data-tips-is-title="true">注意</div>


<div data-tips="true" data-tips-type="warning">seedance 2.0 系列模型不支持直接上传含有真人人脸的参考图/视频。为了便利创作者对肖像的使用，平台推出了一系列解决方案，详情参见seedance 2.0 系列教程的<a href="https://www.volcengine.com/docs/82379/2291680#5c67c9a1">便利创作</a>章节。</div>


**图片要求**


* 传入方式：图片 URL、图片 Base64 编码、素材 ID。

* 图片格式：jpeg、png、webp、bmp、tiff、gif。其中，Seedance 1.5 pro 和 Seedance 2.0 系列模型新增支持 heic 和 heif。

* 单个图片尺寸：

   * 宽高比（宽/高）： [0.4, 2.5]

   * 宽高长度（px）：[300, 6000]

* 大小：单张图片小于 30 MB。请求体大小不超过 64 MB。大文件请勿使用Base64编码。

* 图片数量：

   * 图生视频\-首帧：1 张

   * 图生视频\-首尾帧：2 张

   * seedance 2.0 多模态参考生视频：1~9 张


**视频要求**


* 传入方式：视频URL、素材 ID。

* 视频格式：mp4、mov，支持编码格式见下表。

* 分辨率：480p，720p，1080p，4k

* 时长：单个视频时长 [2, 15] s，最多传入 3 个参考视频，所有视频总时长不超过 15s。

* 单个视频尺寸：

   * 宽高比（宽/高）：[0.4, 2.5]

   * 宽高长度（px）：[300, 6000]

   * 总像素数：[640×640=409600, 3326×2494=8295044]，即宽和高的乘积符合 [409600, 8295044] 的区间要求。

* 大小：单个视频不超过 200 MB。

* 帧率 (FPS)：[24, 60]



|**容器格式** |**常用文件扩展名** |**MIME** |**支持编码** |
|---|---|---|---|
|MP4 |.mp4 |video/mp4 |视频：H.264/AVC、H.265/HEVC<br><br>音频：AAC、MP3 |
|QuickTime |.mov |video/quicktime |视频：H.264/AVC、H.265/HEVC<br><br>音频：AAC、MP3 |


**音频要求**


* 传入方式：音频 URL 、音频 Base64 编码、素材 ID。

* 音频格式：wav、mp3

* 时长：单个音频时长 [2, 15] s，最多传入 3 段参考音频，所有音频总时长不超过 15 s。

* 大小：单个音频不超过 15 MB，请求体大小不超过 64 MB。大文件请勿使用Base64编码。


<span id="2760a484"></span>
## 保存时间


* 任务记录：保存 7 天，查询区间 [T\-7天, T)，T 为请求发起时刻的 UTC 秒级时间戳。

* 视频 URL：保存 24 小时，超时后无法访问，请及时下载或转存。


<span id="b25b1821"></span>
## 限流说明

**模型限流**

**default（在线推理）** 


* RPM 限流：账号下同模型（区分模型版本）每分钟允许创建的任务数量上限。若超过该限制，创建视频生成任务时会报错。

* 并发数限制：账号下同模型（区分模型版本）同一时刻在处理中的任务数量上限。超过此限制的任务将进入队列等待处理。

* 不同模型的限制值不同，详见[视频生成能力](https://www.volcengine.com/docs/82379/1330310#7571da3f)。


**flex（离线推理）** 


* TPD 限流：账号在一天内对同一模型（区分模型版本）的总调用 token 上限。超过此限制的调用请求将被拒绝。不同模型的 TPD 限流值不同，详见[视频生成能力](https://www.volcengine.com/docs/82379/1330310#7571da3f)。


<span id="f76aafc8"></span>
## 图片裁剪规则

**seedance 系列模型的图生视频场景，支持设置生成视频的宽高比** 。当选择的视频宽高与您上传的图片宽高比不一致时，方舟会对您的图片进行裁剪，裁剪时会居中裁剪。详细规则如下：

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">若要呈现出较好的视频效果，建议所指定的视频宽高比（ratio）与实际上传图片的宽高比尽可能接近。</div>



1. 输入参数：

   * 原始图片宽度记为`W`（单位：像素），高度记为`H`（单位：像素）。

   * 目标比例记为`A:B`（例如，21:9），这表示裁剪后的宽度与高度之比应为 `A/B`（如 21/9≈2.333）。

2. 比较宽高比：

* 计算原始图片的宽高比`Ratio_原始=W/H`。

* 计算目标比例的比值`Ratio_目标=A/B`（例如，21:9 的 Ratio目标=21/9≈2.333)。

* 根据比较结果，决定裁剪基准：

   * 如果`Ratio_原始<Ratio_目标`（即原始图片“太高”或“竖高”），则以宽度为基准裁剪。

   * 如果`Ratio_原始>Ratio_目标`（即原始图片“太宽”或“横宽”），则以高度为基准裁剪。

   * 如果相等，则无需裁剪，直接使用全图。

3. 裁剪尺寸计算（量化公式）：

   * 以宽度为基准（适用于竖高图片）：

      * 裁剪宽度`Crop_W=W`（使用整个原始宽度）。

      * 裁剪高度`Crop_H=(B/A)×W`（根据目标比例等比例计算高度）。

      * 裁剪区域的起始坐标（居中定位）：

         * X 坐标（水平）：总是 0（因为宽度全用，从左侧开始）。

         * Y 坐标（垂直）：`(H−Crop_H)/2`（确保垂直居中，从顶部开始）。

   * 以高度为基准（适用于横宽图片）：

      * 裁剪高度`Crop_H=H`（使用整个原始高度）。

      * 裁剪宽度`Crop_W=(A/B)×H`（根据目标比例等比例计算宽度）。

      * 裁剪区域的起始坐标（居中定位）：

         * X 坐标（水平）：`(W−Crop_W)/2`（确保水平居中，从左侧开始）。

         * Y 坐标（垂直）：总是 0（因为高度全用，从顶部开始）。

4. 裁剪结果：

   * 最终裁剪出的图片尺寸为`Crop_W×Crop_H`，比例严格为`A:B`，且完全位于原始图片内部，无黑边。

   * 裁剪区域总是以原始图片中心为基准，因此内容居中。

5. 裁剪示例：

> 以 seedance 1.0 Pro 首帧图生视频功能为例



<span aceTableMode="list" aceTableWidth="2,1,2"></span>
|输入的首帧图片 |指定的宽高比ratio |生成的视频结果 |
|---|---|---|
|16:9<br><br><span>![图片](https://p9-arcosite.byteimg.com/tos-cn-i-goo7wpa0wc/c66d7faff6104320a981b36149dc713f~tplv-goo7wpa0wc-image.image) </span> |21:9 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/6e8590c07be9406d805209355b799a37" controls></video><br> |
||16:9 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/e0bef5f3806f439da5f0c9f5acc44c9b" controls></video><br> |
||4:3 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/a8e3202b77744bec83e0c7baa247b84c" controls></video><br> |
||1:1 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/436df8f6dae74d6c86d08bf1e18bc9d0" controls></video><br> |
||3:4 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/a3a94a577d754501889535a651d03a55" controls></video><br> |
||9:16 |<video src="https://p9-arcosite.byteimg.com/obj/tos-cn-i-goo7wpa0wc/1423ee0fc9cf451398788dc57e9f55c4" controls></video><br> |
