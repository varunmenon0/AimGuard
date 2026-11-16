import csv
import json
import pytest
from aimguard.baseline import digest
from aimguard.event_review import validate,render


def fixture(tmp_path):
    row=dict(review_id='A:0',case_id='A',engagement_id=0,round_id=1,demo='/local/demo.dem',demo_sha256='abc',steamid='1',
        start_tick=10,first_shot_tick=20,end_tick=30,review_status='pending',review_source='unreviewed',
        observed_behavior='unreviewed',assistance_assessment='unreviewed',evidence_reference='',evidence_note='',reviewer='')
    def write_csv(path,rows,fields=None):
        with path.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=fields or list(row));writer.writeheader();writer.writerows(rows)
    template=tmp_path/'event-review-template.csv';write_csv(template,[row])
    queue=dict(role='pending_behavior_review',events=[row],template_sha256=digest(template),manifest_sha256='not_used')
    (tmp_path/'review-queue.json').write_text(json.dumps(queue))
    (tmp_path/'comparison.json').write_text(json.dumps(dict(review_queue_sha256=digest(tmp_path/'review-queue.json'))))
    return row,write_csv


def test_pending_template_does_not_manufacture_event_ground_truth(tmp_path):
    fixture(tmp_path)
    result=validate(tmp_path,tmp_path/'event-review-template.csv',tmp_path/'pending.json')
    assert result['reviewed']==0 and result['pending']==1
    assert not result['training_labels_created'] and result['cheat_activation_ground_truth'] is None


def test_reviewed_observation_retains_provenance_without_becoming_training_label(tmp_path):
    row,write_csv=fixture(tmp_path)
    row.update(review_status='reviewed',review_source='telemetry_only',observed_behavior='tracking',
        assistance_assessment='not_assessable',reviewer='Reviewer',evidence_reference='Demo ticks 10–30',evidence_note='Visibility unavailable.')
    annotations=tmp_path/'annotated.csv';write_csv(annotations,[row])
    result=validate(tmp_path,annotations,tmp_path/'observations.json')
    assert result['reviewed']==1 and result['pending']==0
    assert result['observations'][0]['evidence_note']=='Visibility unavailable.'
    assert result['annotations_sha256']==digest(annotations) and result['training_labels_created'] is False


@pytest.mark.parametrize('change', ['metadata','evidence','confirmed','pending','coverage','duplicate','malformed'])
def test_changed_metadata_and_unsupported_review_claims_fail(tmp_path,change):
    row,write_csv=fixture(tmp_path);rows=[row]
    if change=='metadata':row['first_shot_tick']=21
    elif change=='evidence':row.update(review_status='reviewed',review_source='rendered_gameplay',observed_behavior='aim_correction',assistance_assessment='suspicious')
    elif change=='confirmed':row['assistance_assessment']='confirmed_cheat'
    elif change=='pending':row['observed_behavior']='ordinary_preaim'
    elif change=='coverage':rows=[]
    elif change=='duplicate':rows=[row,row]
    elif change=='malformed':row['evidence_note']=None
    path=tmp_path/'annotations.csv';write_csv(path,rows)
    if change=='malformed':
        text=path.read_text();path.write_text(text.rstrip() + ',extra\n')
    with pytest.raises(ValueError):validate(tmp_path,path,tmp_path/'out.json')
    assert not (tmp_path/'out.json').exists()


def test_queue_and_original_template_receipts_cannot_be_silently_replaced(tmp_path):
    fixture(tmp_path);(tmp_path/'event-review-template.csv').write_text('changed')
    with pytest.raises(ValueError,match='template receipt'):validate(tmp_path,tmp_path/'event-review-template.csv',tmp_path/'out.json')


def test_review_pages_omit_source_label_and_link_exact_window_and_candidate(tmp_path):
    row,write_csv=fixture(tmp_path);pool=tmp_path/'pool';(pool/'tracking').mkdir(parents=True)
    manifest=dict(cases=[dict(case_id='A')]);(pool/'manifest.json').write_text(json.dumps(manifest))
    track=dict(summary=dict(case_id='A',label='secret_source_label'),windows=[dict(engagement_id=0,nearest_before_first_shot='b',tracks=[dict(opponent_id='a'),dict(opponent_id='b')])])
    source=pool/'tracking'/'case_0001.json';source.write_text(json.dumps(track))
    inputs=dict(cases=[dict(case_id='A',tracking_sha256=digest(source))]);(tmp_path/'inputs.json').write_text(json.dumps(inputs))
    queue=json.loads((tmp_path/'review-queue.json').read_text());queue['manifest_sha256']=digest(pool/'manifest.json')
    (tmp_path/'review-queue.json').write_text(json.dumps(queue))
    (tmp_path/'comparison.json').write_text(json.dumps(dict(review_queue_sha256=digest(tmp_path/'review-queue.json'),inputs_sha256=digest(tmp_path/'inputs.json'))))
    render(tmp_path,pool)
    assert 'secret_source_label' not in (tmp_path/'event-pages'/'A-tracks.html').read_text()
    assert '#w=0&amp;t=1' in (tmp_path/'event-pages'/'A.html').read_text()
