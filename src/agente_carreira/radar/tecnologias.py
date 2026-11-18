"""Tecnologias reconhecidas nos anúncios de vaga.

O dicionário do importador de currículo (TECNOLOGIAS_CONHECIDAS) cobre o básico de desenvolvimento. Para
dar nota a uma vaga é preciso reconhecer também o que ela pede e você não tem (SAP, Databricks,
Salesforce...): sem isso, uma vaga que só cita "SQL" entre dez requisitos desconhecidos parecia 100%
compatível.

Ficam de fora nomes curtos ou ambíguos ("R", "C", "Office" casaria com "home office") e variações que
contariam a mesma coisa duas vezes ("Spring Boot" junto de "Spring", "Azure DevOps" junto de "Azure").
"""

from __future__ import annotations

from ..importadores.extrator import TECNOLOGIAS_CONHECIDAS

EXTRAS = [
    # linguagens e frameworks
    "Ruby", "Rails", "Vue.js", "Next.js", "Nuxt", "Svelte", "Laravel", "Django", "Flask", "FastAPI", "Spring",
    "Hibernate", "NestJS", "jQuery", "Bootstrap", "Tailwind", "Sass", "Delphi", "VB.NET", "Visual Basic", "VBA",
    "Scala", "Rust", "Dart", "Elixir", "Perl", "COBOL", "ABAP", "MATLAB", "Xamarin", "MAUI", "Blazor", "WPF",
    "Windows Forms", "Unity", "Unreal",
    # dados
    "Power BI", "Tableau", "Looker", "Qlik", "Databricks", "Spark", "Hadoop", "Airflow", "Kafka", "Snowflake",
    "BigQuery", "dbt", "Pandas", "NumPy", "scikit-learn", "TensorFlow", "PyTorch", "ETL", "Data Factory", "Synapse",
    "SSIS", "SSRS", "DAX", "Power Query", "Pentaho", "Oracle", "Redis", "Elasticsearch", "Cassandra", "DynamoDB",
    "SQLite", "Firebase", "MariaDB", "NoSQL",
    # nuvem, infraestrutura e DevOps
    "GCP", "Google Cloud", "Terraform", "Ansible", "Jenkins", "GitLab", "CI/CD", "Windows Server", "Bash",
    "PowerShell", "Shell Script", "Nginx", "Prometheus", "Grafana", "Zabbix", "VMware", "Hyper-V",
    "Active Directory", "Microsoft 365", "Office 365", "Intune", "SharePoint", "ITIL", "ServiceNow", "GLPI", "Jira",
    "Confluence", "TCP/IP", "DNS", "DHCP", "VPN", "Cisco", "Fortinet", "Firewall", "Wireshark", "Mikrotik",
    # sistemas de gestão
    "SAP", "TOTVS", "Protheus", "Salesforce", "Dynamics 365", "Power Apps", "Power Automate",
    # testes e qualidade
    "Selenium", "Cypress", "Jest", "JUnit", "xUnit", "NUnit", "Postman", "Swagger", "Playwright", "Robot Framework",
    "TDD",
    # arquitetura e integração
    "Microsserviços", "Microservices", "MVC", "gRPC", "RabbitMQ",
    # mobile
    "Android", "iOS",
    # segurança
    "Pentest", "SIEM", "Splunk", "ISO 27001", "OWASP",
    # design
    "Figma",
]

TECNOLOGIAS_VAGAS = list(dict.fromkeys([*TECNOLOGIAS_CONHECIDAS, *EXTRAS]))
