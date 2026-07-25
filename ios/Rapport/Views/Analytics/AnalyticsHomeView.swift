import SwiftUI
import Charts

struct AnalyticsHomeView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: AnalyticsViewModel?

    var body: some View {
        Group {
            if let viewModel, let summary = viewModel.summary {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        kpiGrid(summary.kpis)
                        funnelSection(summary.funnel)
                        byMonthSection(summary.byMonth)
                        bySourceSection(summary.bySource)
                    }
                    .padding()
                }
                .refreshable { await viewModel.load() }
            } else if let viewModel, viewModel.isLoading {
                ProgressView()
            } else if let viewModel, let errorMessage = viewModel.errorMessage {
                ContentUnavailableView("Couldn't load analytics", systemImage: "exclamationmark.triangle", description: Text(errorMessage))
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Analytics")
        .task {
            if viewModel == nil {
                viewModel = AnalyticsViewModel(api: session.analytics)
                await viewModel?.load()
            }
        }
    }

    @ViewBuilder
    private func kpiGrid(_ kpis: AnalyticsSummary.KPIs) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 140))], spacing: 12) {
            KPITile(label: "Total", value: "\(kpis.total)")
            KPITile(label: "Active", value: "\(kpis.active)")
            KPITile(label: "Signed", value: "\(kpis.signed)")
            KPITile(label: "Rejected", value: "\(kpis.rejected)")
            KPITile(label: "Ghosting rate", value: "\(Int(kpis.ghostingRate * 100))%")
            KPITile(label: "Via headhunter", value: "\(Int(kpis.hhPct * 100))%")
        }
    }

    @ViewBuilder
    private func funnelSection(_ funnel: [AnalyticsSummary.FunnelStage]) -> some View {
        VStack(alignment: .leading) {
            Text("Pipeline funnel").font(.headline)
            Chart(funnel) { stage in
                BarMark(x: .value("Count", stage.count), y: .value("Stage", stage.label))
            }
            .frame(height: CGFloat(funnel.count) * 32 + 20)
        }
    }

    @ViewBuilder
    private func byMonthSection(_ months: [AnalyticsSummary.MonthCount]) -> some View {
        VStack(alignment: .leading) {
            Text("Applications by month").font(.headline)
            Chart(months) { month in
                BarMark(x: .value("Month", month.label), y: .value("Count", month.count))
            }
            .frame(height: 180)
        }
    }

    @ViewBuilder
    private func bySourceSection(_ sources: [AnalyticsSummary.SourceCount]) -> some View {
        if !sources.isEmpty {
            VStack(alignment: .leading) {
                Text("By source").font(.headline)
                ForEach(sources) { source in
                    HStack {
                        Text(source.source)
                        Spacer()
                        Text("\(source.count)").foregroundStyle(.secondary)
                    }
                    .font(.subheadline)
                }
            }
        }
    }
}

private struct KPITile: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.title2.bold())
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
