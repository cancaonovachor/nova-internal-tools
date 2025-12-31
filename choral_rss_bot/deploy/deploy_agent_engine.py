"""
Vertex AI Agent Engineへのデプロイスクリプト
"""

import argparse
import os

from dotenv import load_dotenv
from rich.console import Console
from vertexai import agent_engines

load_dotenv()
console = Console()


def deploy_agent(
    project_id: str,
    location: str,
    staging_bucket: str,
    scraper_api_url: str,
    discord_webhook_url: str,
):
    """
    エージェントをVertex AI Agent Engineにデプロイする

    Args:
        project_id: Google CloudプロジェクトID
        location: デプロイ先のリージョン (例: us-central1)
        staging_bucket: Cloud Storageバケット (gs://で始まる)
        scraper_api_url: Cloud RunスクレイピングAPIのURL
        discord_webhook_url: Discord Webhook URL
    """
    import vertexai

    # Vertex AI初期化
    vertexai.init(project=project_id, location=location)

    console.print(f"[bold cyan]Deploying agent to Vertex AI Agent Engine[/bold cyan]")
    console.print(f"Project: {project_id}")
    console.print(f"Location: {location}")
    console.print(f"Staging bucket: {staging_bucket}")

    # エージェントをインポート
    from agent_engine_agent import root_agent

    # AdkAppでラップ
    app = agent_engines.AdkApp(
        agent=root_agent,
        enable_tracing=True,
    )

    # 環境変数を設定してデプロイ
    client = vertexai.Client(project=project_id, location=location)

    console.print("[yellow]Deploying agent...[/yellow]")

    remote_agent = client.agent_engines.create(
        agent=app,
        config={
            "requirements": [
                "google-cloud-aiplatform[agent_engines,adk]>=1.112",
                "google-adk>=0.2.0",
                "requests>=2.31.0",
                "python-dotenv>=1.0.1",
                "rich>=13.9.4",
                "cloudpickle>=3.0.0",
                "pydantic>=2.0.0",
            ],
            "staging_bucket": staging_bucket,
            "env_vars": {
                "SCRAPER_API_URL": scraper_api_url,
                "DISCORD_WEBHOOK_URL": discord_webhook_url,
            },
        },
    )

    console.print(f"[green]Agent deployed successfully![/green]")
    console.print(f"Agent ID: {remote_agent.name}")

    return remote_agent


def test_agent(project_id: str, location: str, agent_id: str, message: str):
    """
    デプロイされたエージェントをテストする

    Args:
        project_id: Google CloudプロジェクトID
        location: デプロイ先のリージョン
        agent_id: エージェントID
        message: テストメッセージ
    """
    import asyncio

    import vertexai

    vertexai.init(project=project_id, location=location)
    client = vertexai.Client(project=project_id, location=location)

    console.print(f"[bold cyan]Testing agent: {agent_id}[/bold cyan]")

    remote_agent = client.agent_engines.get(agent_id)

    async def run_test():
        async for event in remote_agent.async_stream_query(
            user_id="test_user",
            message=message,
        ):
            if hasattr(event, "content"):
                console.print(event.content)

    asyncio.run(run_test())


def delete_agent(project_id: str, location: str, agent_id: str):
    """
    デプロイされたエージェントを削除する

    Args:
        project_id: Google CloudプロジェクトID
        location: デプロイ先のリージョン
        agent_id: エージェントID
    """
    import vertexai

    vertexai.init(project=project_id, location=location)
    client = vertexai.Client(project=project_id, location=location)

    console.print(f"[yellow]Deleting agent: {agent_id}[/yellow]")

    remote_agent = client.agent_engines.get(agent_id)
    remote_agent.delete(force=True)

    console.print(f"[green]Agent deleted successfully![/green]")


def main():
    parser = argparse.ArgumentParser(description="Vertex AI Agent Engine Deploy Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # deploy コマンド
    deploy_parser = subparsers.add_parser("deploy", help="Deploy agent to Agent Engine")
    deploy_parser.add_argument("--project-id", required=True, help="Google Cloud Project ID")
    deploy_parser.add_argument("--location", default="us-central1", help="Region")
    deploy_parser.add_argument("--staging-bucket", required=True, help="Cloud Storage bucket (gs://...)")
    deploy_parser.add_argument("--scraper-api-url", required=True, help="Cloud Run Scraper API URL")
    deploy_parser.add_argument("--discord-webhook-url", help="Discord Webhook URL (optional, can use env)")

    # test コマンド
    test_parser = subparsers.add_parser("test", help="Test deployed agent")
    test_parser.add_argument("--project-id", required=True, help="Google Cloud Project ID")
    test_parser.add_argument("--location", default="us-central1", help="Region")
    test_parser.add_argument("--agent-id", required=True, help="Agent ID")
    test_parser.add_argument("--message", default="新着情報を取得して表示してください", help="Test message")

    # delete コマンド
    delete_parser = subparsers.add_parser("delete", help="Delete deployed agent")
    delete_parser.add_argument("--project-id", required=True, help="Google Cloud Project ID")
    delete_parser.add_argument("--location", default="us-central1", help="Region")
    delete_parser.add_argument("--agent-id", required=True, help="Agent ID")

    args = parser.parse_args()

    if args.command == "deploy":
        discord_webhook = args.discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        deploy_agent(
            project_id=args.project_id,
            location=args.location,
            staging_bucket=args.staging_bucket,
            scraper_api_url=args.scraper_api_url,
            discord_webhook_url=discord_webhook,
        )
    elif args.command == "test":
        test_agent(
            project_id=args.project_id,
            location=args.location,
            agent_id=args.agent_id,
            message=args.message,
        )
    elif args.command == "delete":
        delete_agent(
            project_id=args.project_id,
            location=args.location,
            agent_id=args.agent_id,
        )


if __name__ == "__main__":
    main()
