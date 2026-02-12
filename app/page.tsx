import { Sidebar } from "@/components/layout/sidebar";
import { PageContainer } from "@/components/layout/page-container";
import { Header } from "@/components/layout/header";
import { PortfolioSummary } from "@/components/dashboard/portfolio-summary";
import { ScanStatus } from "@/components/dashboard/scan-status";
import { TopRecommendations } from "@/components/dashboard/top-recommendations";
import { OpenPositions } from "@/components/trades/open-positions";
import { RecentResolutions } from "@/components/dashboard/recent-resolutions";
import { LastScanSummary } from "@/components/dashboard/last-scan-summary";

export default function DashboardPage() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <PageContainer>
          <Header title="Dashboard" actions={<ScanStatus />} />
          <div className="space-y-8">
            <PortfolioSummary />
            <LastScanSummary />
            <OpenPositions />
            <TopRecommendations />
            <RecentResolutions />
          </div>
        </PageContainer>
      </main>
    </div>
  );
}
