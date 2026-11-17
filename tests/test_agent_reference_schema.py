"""The API schema must enforce the references already required by validation."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from supervisao import supervisor_agents as team
from supervisao.supervisor import SupervisorBlocked

class ReferenceSchemaTests(unittest.TestCase):
 def test_schema_requires_existing_reference_for_verdict_and_findings(self):
  schema=team.output_schema({'operation-1'})
  for refs in [schema['properties']['evidencias'],schema['properties']['achados']['items']['properties']['evidencias'],schema['properties']['correcoes']['items']['properties']['evidencias']]:
   self.assertEqual(refs['minItems'],1)
   self.assertEqual(refs['items']['enum'],['operation-1'])
 def test_coordinator_can_only_cite_admitted_references(self):
  schema=team.output_schema({'operation-1'},{'achados':{},'correcoes':{}})
  self.assertEqual(schema['properties']['evidencias']['minItems'],1)
  self.assertEqual(schema['properties']['correcoes']['maxItems'],0)
 def test_validation_still_rejects_unreferenced_approval(self):
  answer={'veredito':'APROVADO','justificativa':'Contrato','proximo_passo':'Executar','evidencias':[],'achados':[],'correcoes':[]}
  with self.assertRaisesRegex(SupervisorBlocked,'APROVACAO_SEM_PROVA'):
   team.validate_answer(answer,{'operation-1'})

 def test_schema_matches_validator_text_and_list_bounds(self):
  schema=team.output_schema({'operation-1'})['properties']
  for key in ('justificativa','proximo_passo'):
   self.assertEqual(schema[key]['maxLength'],1200)
  for key in ('achados','correcoes'):
   self.assertEqual(schema[key]['maxItems'],100)
   for field, spec in schema[key]['items']['properties'].items():
    if spec.get('type')=='string' and 'enum' not in spec:
     self.assertEqual(spec['maxLength'],1200)
