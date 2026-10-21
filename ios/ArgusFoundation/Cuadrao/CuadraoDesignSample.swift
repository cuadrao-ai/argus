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
                                Text("CUADRAO").font(Cuadrao.text(13)).tracking(3)
                            }.fixedSize(horizontal: true, vertical: false)
                        }
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("Novedades", systemImage: "bell") { showingInfo = true }
                        }
                    }
            }.tabItem { Label("Inicio", systemImage: "house") }.tag(0)
            sampleDestination("Plan", symbol: "scope").tag(1)
            sampleDestination("Argus", symbol: "sparkle").tag(2)
            sampleDestination("Buscar", symbol: "magnifyingglass").tag(3)
            sampleDestination("Perfil", symbol: "person.crop.circle").tag(4)
        }
        .tint(Cuadrao.pine).foregroundStyle(Cuadrao.ink).font(Cuadrao.text())
        .sheet(isPresented: $showingInfo) { sampleNotice }
    }

    private func sampleDestination(_ title: String, symbol: String) -> some View {
        NavigationStack {
            VStack(spacing: 20) {
                CuadraoSymbol(name: symbol)
                Text(title).font(Cuadrao.title())
                Text("Esta muestra explora Inicio, cuentas y registrar un gasto.")
                    .foregroundStyle(Cuadrao.muted).multilineTextAlignment(.center)
                Button("Volver a Inicio") { selectedTab = 0 }.buttonStyle(CuadraoPrimaryButton())
            }.padding(30).frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Cuadrao.paper)
        }.tabItem { Label(title, systemImage: symbol) }
    }

    private var sampleNotice: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Muestra de diseño").font(Cuadrao.title())
            Text("Datos de ejemplo. Puedes registrar un gasto y ver cómo cambia la cuenta. Nada se envía ni modifica tus cuentas reales.")
            Text("Los cambios se reinician al cerrar la muestra.").foregroundStyle(Cuadrao.muted)
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
                    Text("PERSONAL").font(Cuadrao.text(11)).tracking(2).foregroundStyle(Cuadrao.muted)
                    Text("Tu dinero,\nen su lugar.").font(Cuadrao.title(38)).lineSpacing(-3)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Saldo registrado").font(Cuadrao.text(13)).foregroundStyle(Cuadrao.muted)
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("DOP").font(Cuadrao.text(14)).foregroundStyle(Cuadrao.muted)
                            Text(Cuadrao.money(data.total)).font(Cuadrao.text(33)).monospacedDigit()
                                .minimumScaleFactor(0.7).lineLimit(1)
                        }
                    }.padding(.top, 5)
                }
                VStack(spacing: 0) {
                    HStack {
                        CuadraoSectionTitle(title: "Cuentas")
                        Spacer()
                        Button { showAdd = true } label: { Image(systemName: "plus") }
                            .accessibilityLabel("Añadir cuenta")
                            .frame(width: 44, height: 44)
                        Button { showAccounts = true } label: { Image(systemName: "ellipsis") }
                            .accessibilityLabel("Opciones de cuentas")
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
                    CuadraoSectionTitle(title: "Últimos movimientos")
                    ForEach(data.expenses.prefix(3)) { expense in
                        CuadraoExpenseRow(expense: expense)
                    }
                }
            }.padding(.horizontal, 24).padding(.top, 24).padding(.bottom, 30)
        }.background(Cuadrao.paper)
            .toolbarBackground(Cuadrao.paper, for: .navigationBar)
            .sheet(isPresented: $showAccounts) {
                NavigationStack {
                    List { Text("No hay cuentas archivadas") }
                        .navigationTitle("Cuentas archivadas").navigationBarTitleDisplayMode(.inline)
                        .scrollContentBackground(.hidden).background(Cuadrao.paper)
                        .toolbar { CuadraoDoneToolbar(title: "Listo") { showAccounts = false } }
                }.presentationDetents([.medium]).presentationDragIndicator(.visible)
            }
            .alert("Añadir cuenta", isPresented: $showAdd) {
                Button("Entendido", role: .cancel) { }
            } message: { Text("Esta muestra se concentra en abrir una cuenta y registrar un gasto. La creación de cuentas sigue en la app conectada.") }
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
