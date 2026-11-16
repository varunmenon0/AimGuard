import io
import zipfile
import zlib
import pandas as pd
import pytest
from aimguard.source_anchors import (parse_frame_ranges,unique_rounded_identity,map_frame_window,
    cached_member,choose_candidate,image_elimination_identity,source_text,CASE_MAP)


def frame():
    return pd.DataFrame(dict(steamid=['2']*2+['1']*4,tick=[1,2,100,101,102,103],
        kill_num=[1,1,7,7,7,7],match_id=['other']*2+['g-match']*4,isKilling=[False,True,False,False,True,False]))


def test_frame_ids_parse_as_data_without_executing_script_and_reject_bad_bounds():
    assert parse_frame_ranges('const frameRanges = {"Case C":{"1":[8,11],},};')=={'Case C':{'1':[8,11]}}
    for text in ('const frameRanges = alert(1);','const frameRanges = {"Case C":{"1":[-1,3]}};',
                 'const frameRanges = {"Case C":{"1":[5,3]}};'):
        with pytest.raises(ValueError):parse_frame_ranges(text)


def test_row_indices_stay_distinct_from_replay_ticks_and_full_batch_is_not_reset_per_player():
    result=map_frame_window(frame(),[2,5],'1',['1','2'],{102})
    assert result['published_frame_start']==2 and result['replay_start_tick']==100
    assert result['replay_kill_tick']==102 and result['activation_ground_truth'] is None
    assert result['rendered_gameplay_review']=='pending'
    with pytest.raises(ValueError,match='outside'):map_frame_window(frame().iloc[2:].reset_index(drop=True),[2,5],'1',['1','2'],{102})


def test_rounded_identity_requires_unique_exact_replay_member_not_integer_conversion():
    assert unique_rounded_identity('1.0',['1','2'])=='1'
    with pytest.raises(ValueError,match='uniquely'):unique_rounded_identity('76561199000000000',['76561199000000000','76561199000000001'])
    with pytest.raises(ValueError):unique_rounded_identity('nan',['1'])


@pytest.mark.parametrize('corruption',['identity','gap','multiple_kills','different_elimination','no_event','invalid_flag'])
def test_inconsistent_source_rows_fail_instead_of_inventing_activation(corruption):
    data=frame();kills={102}
    if corruption=='identity':data.loc[3,'steamid']='2'
    elif corruption=='gap':data.loc[4,'tick']=104
    elif corruption=='multiple_kills':data.loc[3,'isKilling']=True
    elif corruption=='different_elimination':data.loc[3,'kill_num']=8
    elif corruption=='no_event':kills=set()
    elif corruption=='invalid_flag':data['isKilling']=data.isKilling.astype(str);data.loc[3,'isKilling']='unknown'
    with pytest.raises(ValueError):map_frame_window(data,[2,5],'1',['1','2'],kills)


def test_multiple_matching_batches_require_independent_elimination_identity():
    candidates=[dict(elimination=21,member='old'),dict(elimination=41,member='correct')]
    with pytest.raises(ValueError,match='ambiguous'):choose_candidate(candidates)
    assert choose_candidate(candidates,41)['member']=='correct'
    with pytest.raises(ValueError):choose_candidate(candidates,99)


def test_archive_copy_metadata_disambiguates_case_without_becoming_a_behavior_label():
    index=[dict(name='a/5.7_Case_Study/elimination_scope/CaseE/tra_1/velocity_x_shap_value_1400.png',size=100,crc=20),
        dict(name='a/1.0_41_g-match/velocity_x_shap_value_1400.png',size=100,crc=20)]
    assert image_elimination_identity(index,'Case E','1',[1344,1439],dict(match_id='g-match',steamid='1'))==41
    assert CASE_MAP['2B'][1]=='author_described_wallhack_only'
    assert source_text('<p>Case <b>D</b></p>')=='Case D'


def test_cached_zip_member_is_crc_checked_and_truncation_fails(tmp_path):
    path=tmp_path/'cache.partial';payload=b'local original source CSV'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:archive.writestr('source.csv',payload)
    with zipfile.ZipFile(path) as archive:
        info=archive.getinfo('source.csv');entry=dict(name=info.filename,offset=info.header_offset,compressed=info.compress_size,size=info.file_size,crc=info.CRC)
    assert cached_member(path,entry)==payload
    with pytest.raises(ValueError,match='CRC'):cached_member(path,dict(entry,crc=0))
    path.write_bytes(path.read_bytes()[:20])
    with pytest.raises(ValueError):cached_member(path,entry)
