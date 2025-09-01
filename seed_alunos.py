# seed_alunos.py
# execute with: py manage.py shell -c "import django; django.setup(); exec(open('seed_alunos.py','r',encoding='utf-8').read())"

from django.apps import apps
from django.contrib.auth.models import Group

U = apps.get_model("accounts", "User")

DATA = [
    {"cpf":"55263863845","first_name":"Ana","last_name":"Silva","email":"ana.silva.3845@example.com"},
    {"cpf":"90064083870","first_name":"Beatriz","last_name":"Souza","email":"beatriz.souza.3870@example.com"},
    {"cpf":"70470793511","first_name":"Bianca","last_name":"Oliveira","email":"bianca.oliveira.3511@example.com"},
    {"cpf":"56230553899","first_name":"Camila","last_name":"Santos","email":"camila.santos.3899@example.com"},
    {"cpf":"90230748406","first_name":"Carla","last_name":"Lima","email":"carla.lima.8406@example.com"},
    {"cpf":"77060322485","first_name":"Daniela","last_name":"Pereira","email":"daniela.pereira.2485@example.com"},
    {"cpf":"37801770994","first_name":"Eduarda","last_name":"Ferreira","email":"eduarda.ferreira.0994@example.com"},
    {"cpf":"28942690211","first_name":"Fernanda","last_name":"Almeida","email":"fernanda.almeida.0211@example.com"},
    {"cpf":"47360989531","first_name":"Gabriela","last_name":"Gomes","email":"gabriela.gomes.9531@example.com"},
    {"cpf":"23415605981","first_name":"Isabela","last_name":"Costa","email":"isabela.costa.5981@example.com"},
    {"cpf":"94705730569","first_name":"Júlia","last_name":"Ribeiro","email":"julia.ribeiro.0569@example.com"},
    {"cpf":"57984682755","first_name":"Larissa","last_name":"Carvalho","email":"larissa.carvalho.2755@example.com"},
    {"cpf":"29877916231","first_name":"Luana","last_name":"Araujo","email":"luana.araujo.6231@example.com"},
    {"cpf":"86309522965","first_name":"Marina","last_name":"Martins","email":"marina.martins.2965@example.com"},
    {"cpf":"03027011332","first_name":"Natália","last_name":"Rocha","email":"natalia.rocha.1332@example.com"},
    {"cpf":"98629053526","first_name":"Paula","last_name":"Dias","email":"paula.dias.3526@example.com"},
    {"cpf":"47895063634","first_name":"Sabrina","last_name":"Moreira","email":"sabrina.moreira.3634@example.com"},
    {"cpf":"93408407630","first_name":"Vitória","last_name":"Teixeira","email":"vitoria.teixeira.7630@example.com"},
    {"cpf":"55984547775","first_name":"Sofia","last_name":"Correia","email":"sofia.correia.7775@example.com"},
    {"cpf":"61443976717","first_name":"Helena","last_name":"Monteiro","email":"helena.monteiro.6717@example.com"},
    {"cpf":"58388748645","first_name":"Alex","last_name":"Castro","email":"alex.castro.8645@example.com"},
    {"cpf":"37281264119","first_name":"Ariel","last_name":"Mendes","email":"ariel.mendes.4119@example.com"},
    {"cpf":"18800225322","first_name":"Dani","last_name":"Nunes","email":"dani.nunes.5322@example.com"},
    {"cpf":"17272050225","first_name":"Sam","last_name":"Barros","email":"sam.barros.0225@example.com"},
]

group, _ = Group.objects.get_or_create(name="Aluno")

created = 0
for d in DATA:
    u, was_created = U.objects.update_or_create(
        cpf=d["cpf"],
        defaults={
            "first_name": d["first_name"],
            "last_name":  d["last_name"],
            "email":      d["email"],
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        },
    )
    if was_created:
        created += 1
    u.set_password("hango.teste123")
    u.save()
    u.groups.add(group)

print(f"Done. {created} created, {len(DATA)-created} updated. Group=Aluno")
