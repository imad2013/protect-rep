# AGENTS.md

## Project Overview

Java 11 Maven WAR web application (`webapp-210401210447`) deployed to Azure Web App via GitHub Actions. Uses Servlet API 4.0 with Jetty for local development.

## Cursor Cloud specific instructions

### System Dependencies

- **Java 11** (OpenJDK) — required by the CI/CD workflow (`.github/workflows/master_webapp-210401210447.yml`). Must be the active `java` alternative; set via `update-alternatives --set java /usr/lib/jvm/java-11-openjdk-amd64/bin/java`.
- **JAVA_HOME** must be `/usr/lib/jvm/java-11-openjdk-amd64` (persisted in `~/.bashrc`).
- **Maven 3.8+** — installed from Ubuntu packages.

### Key Commands

| Task | Command |
|------|---------|
| Build + test | `mvn clean install` |
| Run dev server | `mvn jetty:run` (serves on port 8080) |
| Run tests only | `mvn test` |
| Package WAR | `mvn package` |

### Gotchas

- The Jetty dev server (`mvn jetty:run`) runs in the foreground and blocks the terminal. Use background execution (`&`) if you need to curl against it in the same shell session.
- The CI/CD workflow produces `target/*.war` — this path pattern is used by the GitHub Actions upload step.
- There is no linter configured for this Java project beyond the Maven compiler plugin (which catches compilation errors).
- The `.gitignore` was originally for ActionScript/Flash — `target/` and IDE directories have been appended.
