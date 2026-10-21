import SwiftUI

struct CuadraoAccountDetail: View {
    let data: CuadraoSampleData
    let accountID: String
    @State private var showExpense = false
    @State private var showRename = false
    @State private var name = ""

    private var account: CuadraoSampleAccount? { data.accounts.first { $0.id == accountID } }

    var body: some View {
        if let account {
            ScrollView {
                VStack(alignment: .leading, spacing: 30) {
                    VStack(alignment: .leading, spacing: 18) {
                        CuadraoSymbol(name: account.symbol)
                        Text(account.name).font(Cuadrao.title(34))
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Saldo registrado").font(Cuadrao.text(13)).foregroundStyle(Cuadrao.muted)
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text("DOP").font(Cuadrao.text(14)).foregroundStyle(Cuadrao.muted)
                                Text(Cuadrao.money(data.balance(account))).font(Cuadrao.text(36)).monospacedDigit()
                                    .minimumScaleFactor(0.7).lineLimit(1)
                            }
                        }
                    }.padding(.top, 12)
                    Button("Registrar gasto") { showExpense = true }.buttonStyle(CuadraoPrimaryButton())
                    VStack(alignment: .leading, spacing: 14) {
                        HStack {
                            CuadraoSectionTitle(title: "Actividad")
                            Spacer()
                            Text("DOP").font(Cuadrao.text(12)).foregroundStyle(Cuadrao.muted)
                        }
                        Text("HOY").font(Cuadrao.text(11)).tracking(2).foregroundStyle(Cuadrao.muted)
                        ForEach(data.expenses.filter { $0.accountID == accountID }) { expense in
                            CuadraoExpenseRow(expense: expense)
                            Rectangle().fill(Cuadrao.line).frame(height: 0.5)
                        }
                    }
                }.padding(.horizontal, 24).padding(.bottom, 32)
            }.background(Cuadrao.paper)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button("Cambiar nombre", systemImage: "pencil") {
                                name = account.name
                                showRename = true
                            }
                            Button("Registrar gasto", systemImage: "plus") { showExpense = true }
                        } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                        .accessibilityLabel("Opciones de cuenta")
                    }
                }
                .sheet(isPresented: $showExpense) {
                    CuadraoExpenseSheet(data: data, account: account)
                        .presentationDragIndicator(.visible)
                        .presentationBackground(Cuadrao.paper)
                }
                .alert("Cambiar nombre", isPresented: $showRename) {
                    TextField("Nombre", text: $name)
                    Button("Cancelar", role: .cancel) { }
                    Button("Guardar") {
                        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !trimmed.isEmpty, let index = data.accounts.firstIndex(where: { $0.id == accountID }) {
                            data.accounts[index].name = trimmed
                        }
                    }
                }
        }
    }
}

struct CuadraoExpenseSheet: View {
    let data: CuadraoSampleData
    let account: CuadraoSampleAccount
    @Environment(\.dismiss) private var dismiss
    @State private var amount = ""
    @State private var note = ""
    @State private var category = "Comida"
    @FocusState private var amountFocused: Bool

    private var cents: Int? {
        let normalized = amount.replacingOccurrences(of: ",", with: ".")
        guard let number = Decimal(string: normalized), number > 0, number <= Decimal(string: "9999999.99")! else { return nil }
        return NSDecimalNumber(decimal: number * 100).intValue
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    HStack(spacing: 12) {
                        CuadraoSymbol(name: account.symbol)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(account.name).font(Cuadrao.text(15))
                            Text("Desde esta cuenta").font(Cuadrao.text(12)).foregroundStyle(Cuadrao.muted)
                        }
                    }
                    VStack(alignment: .leading, spacing: 14) {
                        Text("¿Cuánto gastaste?").font(Cuadrao.title(30))
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Text("DOP").font(Cuadrao.text(17)).foregroundStyle(Cuadrao.muted)
                            TextField("0.00", text: $amount)
                                .keyboardType(.decimalPad).focused($amountFocused)
                                .font(Cuadrao.text(40)).monospacedDigit().multilineTextAlignment(.trailing)
                                .accessibilityLabel("Monto del gasto")
                                .onChange(of: amount) { _, newValue in amount = cleanAmount(newValue) }
                        }.padding(18).background(Cuadrao.raised, in: RoundedRectangle(cornerRadius: 12))
                            .overlay { RoundedRectangle(cornerRadius: 12).stroke(Cuadrao.line, lineWidth: 1) }
                    }
                    VStack(spacing: 0) {
                        HStack {
                            Text("Categoría")
                            Spacer()
                            Picker("Categoría", selection: $category) {
                                ForEach(["Comida", "Compras", "Transporte", "Hogar", "Sin categoría"], id: \.self) { Text($0) }
                            }.labelsHidden().tint(Cuadrao.ink)
                        }.padding(.vertical, 10)
                        Divider().overlay(Cuadrao.line)
                        TextField("Nota (opcional)", text: $note)
                            .textInputAutocapitalization(.sentences).padding(.vertical, 20)
                    }.font(Cuadrao.text())
                }.padding(24)
            }
            .cuadraoFormKeyboard()
            .background(Cuadrao.paper)
            .navigationTitle("Registrar gasto").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: "Cancelar") { dismiss() }
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 12) {
                    Button("Guardar gasto") {
                        guard let cents else { return }
                        let title = note.trimmingCharacters(in: .whitespacesAndNewlines)
                        data.expenses.insert(CuadraoSampleExpense(accountID: account.id,
                            title: title.isEmpty ? category : title, category: category, cents: cents), at: 0)
                        dismiss()
                    }.buttonStyle(CuadraoPrimaryButton()).disabled(cents == nil)
                }.padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 12)
                    .background(Cuadrao.paper)
            }
        }.tint(Cuadrao.pine).font(Cuadrao.text()).foregroundStyle(Cuadrao.ink)
    }

    private func cleanAmount(_ input: String) -> String {
        var result = ""
        var decimal = false
        var fraction = 0
        var integer = 0
        for character in input {
            if character == "." || character == "," {
                if !decimal { result += "."; decimal = true }
            } else if character.isASCII && character.isNumber {
                if decimal && fraction < 2 { result.append(character); fraction += 1 }
                else if !decimal && integer < 7 { result.append(character); integer += 1 }
            }
        }
        return result
    }
}

#Preview("Cuadrao · Account") {
    NavigationStack { CuadraoAccountDetail(data: CuadraoSampleData(), accountID: "daily") }
        .tint(Cuadrao.pine).preferredColorScheme(.light)
}
