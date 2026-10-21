import SwiftUI

struct CuadraoDesignSample: View {
    @State private var data = CuadraoSampleData()
    @State private var selectedTab = 0
    @State private var showingInfo = false

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                CuadraoHome(data: data)
                    .toolbar {
                        ToolbarItem(placement: .topBarLeading) {
                            HStack(spacing: 10) {
                                CuadraoMark()
                                Text(CuadraoCopy.text("copy.cuadraoDesignSample.35f083d4f4", spanish: CuadraoCopy.isSpanish())).font(Cuadrao.text(13)).tracking(3)
                            }.fixedSize(horizontal: true, vertical: false)
                        }
                        ToolbarItem(placement: .topBarTrailing) {
                            Button(CuadraoCopy.text("copy.cuadraoHomePresentation.41483aed95"), systemImage: "bell") { showingInfo = true }
                        }
                    }
            }.tabItem { Label(CuadraoCopy.text("destination.home"), systemImage: "house") }.tag(0)
            sampleDestination(CuadraoCopy.text("destination.plan"), symbol: "scope").tag(1)
            sampleDestination(CuadraoCopy.text("destination.argus"), symbol: "sparkle").tag(2)
            sampleDestination(CuadraoCopy.text("destination.search"), symbol: "magnifyingglass").tag(3)
            sampleDestination(CuadraoCopy.text("sheet.profile"), symbol: "person.crop.circle").tag(4)
        }
        .tint(Cuadrao.pine).foregroundStyle(Cuadrao.ink).font(Cuadrao.text())
        .sheet(isPresented: $showingInfo) { sampleNotice }
    }

    private func sampleDestination(_ title: String, symbol: String) -> some View {
        NavigationStack {
            VStack(spacing: 20) {
                CuadraoSymbol(name: symbol)
                Text(title).font(Cuadrao.title())
                Text(CuadraoCopy.text("copy.cuadraoDesignSample.8a26df145b", spanish: CuadraoCopy.isSpanish()))
                    .foregroundStyle(Cuadrao.muted).multilineTextAlignment(.center)
                Button(CuadraoCopy.text("copy.cuadraoDesignSample.c1411df892", spanish: CuadraoCopy.isSpanish())) { selectedTab = 0 }.buttonStyle(CuadraoPrimaryButton())
            }.padding(30).frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Cuadrao.paper)
        }.tabItem { Label(title, systemImage: symbol) }
    }

    private var sampleNotice: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(CuadraoCopy.text("copy.cuadraoDesignSample.0b07f6aa15", spanish: CuadraoCopy.isSpanish())).font(Cuadrao.title())
            Text(CuadraoCopy.text("copy.cuadraoDesignSample.64c79d3021", spanish: CuadraoCopy.isSpanish()))
            Text(CuadraoCopy.text("copy.cuadraoDesignSample.4be5e39052", spanish: CuadraoCopy.isSpanish())).foregroundStyle(Cuadrao.muted)
        }.padding(28).presentationDetents([.medium]).presentationDragIndicator(.visible)
            .presentationBackground(Cuadrao.paper)
    }
}

struct CuadraoHome: View {
    let data: CuadraoSampleData
    @State private var showAccounts = false
    @State private var showAdd = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                VStack(alignment: .leading, spacing: 14) {
                    Text(CuadraoCopy.text("copy.cuadraoDesignSample.0dcbf7a4c1", spanish: CuadraoCopy.isSpanish())).font(Cuadrao.text(11)).tracking(2).foregroundStyle(Cuadrao.muted)
                    Text(CuadraoCopy.text("copy.cuadraoDesignSample.62bef1971d", spanish: CuadraoCopy.isSpanish())).font(Cuadrao.title(38)).lineSpacing(-3)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(CuadraoCopy.text("loop.recorded")).font(Cuadrao.text(13)).foregroundStyle(Cuadrao.muted)
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("DOP").font(Cuadrao.text(14)).foregroundStyle(Cuadrao.muted)
                            Text(Cuadrao.money(data.total)).font(Cuadrao.text(33)).monospacedDigit()
                                .minimumScaleFactor(0.7).lineLimit(1)
                        }
                    }.padding(.top, 5)
                }
                VStack(spacing: 0) {
                    HStack {
                        CuadraoSectionTitle(title: CuadraoCopy.text("copy.connectedCuadraoHome.8cce5d02a3"))
                        Spacer()
                        Button { showAdd = true } label: { Image(systemName: "plus") }
                            .accessibilityLabel(CuadraoCopy.text("copy.connectedCuadraoHome.10d1d9ce3f"))
                            .frame(width: 44, height: 44)
                        Button { showAccounts = true } label: { Image(systemName: "ellipsis") }
                            .accessibilityLabel(CuadraoCopy.text("copy.cuadraoDesignSample.bfc8ad4ba8", spanish: CuadraoCopy.isSpanish()))
                            .frame(width: 44, height: 44)
                    }.padding(.bottom, 6)
                    ForEach(data.active) { account in
                        NavigationLink {
                            CuadraoAccountDetail(data: data, accountID: account.id)
                        } label: {
                            HStack(spacing: 13) {
                                CuadraoSymbol(name: account.symbol)
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(account.name).font(Cuadrao.text(15))
                                    Text(account.kind).font(Cuadrao.text(12)).foregroundStyle(Cuadrao.muted)
                                }
                                Spacer(minLength: 4)
                                Text(Cuadrao.money(data.balance(account))).font(Cuadrao.text(15)).monospacedDigit()
                                Image(systemName: "chevron.right").font(.system(size: 10)).foregroundStyle(Cuadrao.muted)
                            }.padding(.vertical, 15).contentShape(Rectangle())
                        }.buttonStyle(.plain)
                        Rectangle().fill(Cuadrao.line).frame(height: 0.5)
                    }
                }
                VStack(alignment: .leading, spacing: 16) {
                    CuadraoSectionTitle(title: CuadraoCopy.text("copy.cuadraoDesignSample.266336b705", spanish: CuadraoCopy.isSpanish()))
                    ForEach(data.expenses.prefix(3)) { expense in
                        CuadraoExpenseRow(expense: expense)
                    }
                }
            }.padding(.horizontal, 24).padding(.top, 24).padding(.bottom, 30)
        }.background(Cuadrao.paper)
            .toolbarBackground(Cuadrao.paper, for: .navigationBar)
            .sheet(isPresented: $showAccounts) {
                NavigationStack {
                    List { Text(CuadraoCopy.text("copy.connectedCuadraoHome.63cbd4a9dc")) }
                        .navigationTitle(CuadraoCopy.text("copy.connectedCuadraoHome.4ab8767f26")).navigationBarTitleDisplayMode(.inline)
                        .scrollContentBackground(.hidden).background(Cuadrao.paper)
                        .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.cuadraoHomeCanvas.1756cbfe73")) { showAccounts = false } }
                }.presentationDetents([.medium]).presentationDragIndicator(.visible)
            }
            .alert(CuadraoCopy.text("copy.connectedCuadraoHome.10d1d9ce3f"), isPresented: $showAdd) {
                Button(CuadraoCopy.text("auth.apple.capture.dismiss"), role: .cancel) { }
            } message: { Text(CuadraoCopy.text("copy.cuadraoDesignSample.14600a36e6", spanish: CuadraoCopy.isSpanish())) }
    }
}

struct CuadraoExpenseRow: View {
    let expense: CuadraoSampleExpense
    var body: some View {
        HStack(spacing: 13) {
            Image(systemName: expense.category == "Comida" ? "fork.knife" : "bag")
                .frame(width: 44).foregroundStyle(Cuadrao.muted)
            VStack(alignment: .leading, spacing: 5) {
                Text(expense.title).font(Cuadrao.text(15))
                Text(expense.category).font(Cuadrao.text(12)).foregroundStyle(Cuadrao.muted)
            }
            Spacer()
            Text("−" + Cuadrao.money(expense.cents)).monospacedDigit().font(Cuadrao.text(15))
        }.padding(.vertical, 9)
    }
}

#Preview("Cuadrao · Home") {
    CuadraoDesignSample().preferredColorScheme(.light)
}
