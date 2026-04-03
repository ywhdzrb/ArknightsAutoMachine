# .github 目录

## 目录说明

本目录包含 GitHub 相关的配置和模板文件，用于项目管理、CI/CD 自动化和社区协作。

## 子目录结构

### workflows/
- **ci.yml**: 跨平台构建矩阵（Windows/Linux/macOS）
- **release.yml**: 自动化发版流程
- **codeql.yml**: 静态安全分析（CodeQL）

### ISSUE_TEMPLATE/
- 问题报告模板
- 功能请求模板
- Bug 报告模板

### 文件
- **CODE_OF_CONDUCT.md**: 社区行为准则
- **CONTRIBUTING.md**: 贡献者指南

## 维护说明

- 所有工作流文件使用 GitHub Actions 语法
- CI 矩阵覆盖 Debug/Release/RelWithDebInfo 三种构建类型
- 代码质量门集成 SonarCloud、Codecov、Clang-Tidy

## 相关文档

- [CI/CD 配置文档](../docs/dev-setup.md)
- [贡献指南](./CONTRIBUTING.md)
