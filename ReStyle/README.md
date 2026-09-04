# LiveMngSys ReStyle WSS

独立的本地 Web Style System 管理页，用于整理与试验 LiveMngSys 的布局、组件和设计令牌。

## 使用

双击 `Start-ReStyle.bat` 可在 `7650` 端口启动本地页面并打开浏览器。直接打开 `index.html` 可以预览，但磁盘保存功能需要本地服务；图标 CDN 不可用时不影响主要功能。

- 在“全局布局”“可复用组件”中点击铅笔按钮进入编辑器。
- 组件目录采用“一张卡片一个组件”的粒度，并按输入控件、操作控件、数据展示、反馈组件和直播业务分类。
- HTML、CSS、JS 分栏编辑，右侧 iframe 实时预览。
- 编辑器支持格式化、基础语法着色、代码字体和逐行中文释义；释义会说明常见枚举值与用途。
- 代码、行号和中文释义使用贯穿式交替行底色；代码区、预览区和释义区分隔线均可拖拽调整。
- 预览窗格提供缩小、放大和重置缩放按钮。
- HTML 编辑行与预览元素支持双向悬停定位：代码行高亮对应元素框线，预览元素反向高亮源码行。
- `Ctrl+S` 或“保存到本地目录”会将 HTML、CSS、JS 和元数据分别写入 `ReStyle/saved` 下的相对路径，并同步更新浏览器项目树。
- “设计令牌”页对应当前 `GUIDemo/style.css` 的 `:root` 变量，可逐项编辑、保存、恢复和复制 CSS。
- “项目树”可继续编辑已保存内容，也可导出完整 JSON。
- `assets/avatar-sample.png`、`project-dark.jpg`、`project-light.jpg` 复用了 GUIDemo 的现有素材；原文件未修改。

## 文件

- `index.html`：应用骨架与编辑器结构
- `styles.css`：WSS 管理页自身的界面样式与响应式规则
- `app.js`：组件目录、预览、编辑、保存和导出逻辑
- `server.py`：本地静态服务和受限磁盘保存接口
- `saved/`：组件源码的本地保存根目录
- `Start-ReStyle.bat`：7650 端口一键启动脚本

当前产物严格限制在 `ReStyle` 目录，未修改 LiveMngSys 其他文件。
