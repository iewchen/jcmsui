
var global_mice = undefined;
var global_cages = undefined;
var global_racks = undefined;
var global_strains = undefined;
var global_mating_mice = undefined;
var global_strain_filter_toggle = -1;
var global_mdl_filter_toggle = undefined;
var nbsp = '&nbsp;&nbsp;&nbsp;&nbsp;';
const DAY = 86400000;

$(document).ready(function(){
    $('[data-toggle="tooltip"]').tooltip();

    let pathname = window.location.pathname;
    if (pathname.endsWith('litter.html')) {
        loadlitters();
    } else {
        loadrack();
    }
})

// compare two date and return a string as css class name for highlight
function compare_date(now, dt) {
    let t_now = now.getTime();
    let t_dt = dt.getTime();
    if (t_dt < t_now) {
        highlight_class = 'wean-warning';
    } else if (t_dt < (t_now + 3 * DAY)) {
        highlight_class = 'wean-attention';
    } else {
        highlight_class = '';
    }

    return highlight_class;
}

function calc_age(dob) {
    let now = new Date();
    let birth = new Date(dob + 'T00:00:00');
    return Math.floor((now - birth) / DAY);
}

function loadlitters() {
    $.ajax({
        type: 'GET',
        url: 'api/litters.json?t=' + Math.random(),
        success: function(data) {
            let m = data.mice;   /* map mouse key to tag */
            let tmp = '<h2>Litters</h4>';
            tmp += '<table><tbody>';
            tmp += '<tr><th>ID</th><th>Strain</th><th>Pups</th><th>DOB</th><th>Age(d)</th><th>WeanDate</th><th>Comment</th> <th>Dam1</th><th>Dam1 Cage</th><th>Dam2</th> <th>Sire</th> </tr>';

            let litterscount = {};
            let now = new Date();
            let wean, wean_cls;
            $.each(data.litters, function(i, lt) {
                tmp += '<tr><td>' + lt.id + '</td>';
                tmp += '<td>' + lt.strain + '</td>';
                tmp += '<td>' + lt.born + '</td>';
                tmp += '<td>' + lt.dob + '</td>';
                tmp += '<td>' + calc_age(lt.dob) + '</td>';

                wean = new Date(lt.wean + 'T00:00:00');
                wean_cls = compare_date(now, wean);
                tmp += '<td class="' + wean_cls + '">' + lt.wean + '</td>';
                tmp += '<td>' + lt.comment + '</td>';

                tmp += '<td class="clickable-cell showmousedetail" data-mouse-key="' + lt.dam1 + '">' + m[lt.dam1].tag + '</td>';
                tmp += '<td>' + m[lt.dam1].cage + '</td>';

                let dam2tag = m[lt.dam2] ? m[lt.dam2].tag : '';
                tmp += '<td class="clickable-cell showmousedetail" data-mouse-key="' + lt.dam2 + '">' + dam2tag + '</td>';
                tmp += '<td class="clickable-cell showmousedetail" data-mouse-key="' + lt.sire + '">' + m[lt.sire].tag + '</td>';
                tmp += '</tr>';

                if (litterscount[lt.strain] === undefined)
                    litterscount[lt.strain] = 0;
                litterscount[lt.strain] += lt.born;
            })

            tmp += '</tbody></table>';
            $('#litter-container').html(tmp);

            litterscount_tbl = Object.keys(litterscount).map(key =>
                [key, litterscount[key]]);
            count = litterscount_tbl.reduce((acum, cur) => {
                acum += cur[1];
                return acum;
            }, 0)

            litterscount_tbl.unshift(['Strain', 'Born']);
            litterscount_tbl.push(['Total', count]);
            makeTable($('#litterscount'), litterscount_tbl);
        }
    });
}


function fmt_rack(rack) {
    let tmp = '';
    let ncages = 0;
    $.each(rack, function(r, cage_ids) {
        tmp += '<div class="rack-row" id="rack-row-' + r + '">';
        $.each(cage_ids, function(i, cage_id) {
            let cage = global_cages[cage_id];
            let cage_name = cage.name;
            if (cage.hide === 1)  // cage is filter out
                return;  // skip loop

            tmp += '<div class="cage" id="cage-' + cage_id + '">';
            tmp += '<h4>Rack: ' + cage_name.toUpperCase() + '</h4>';
            tmp += 'Empty</div>';
            ncages += 1;
        })

        tmp += '</div>';
    })

    if (ncages == 0)
        tmp = '';

    return tmp;
}

// modify global_cages insitu
function filter_cages_by_strain(strain_name, sex) {
    $.each(global_cages, function(cage_id, cage){
        cage.hide = 1;
        $.each(cage.micelist, (i, mk) => {
            m_strain = global_mice[mk]['strain'];
            m_sex = global_mice[mk]['sex'];
            if (sex == undefined) {
                if (m_strain == strain_name) {
                    cage.hide = 0;
                    return false; // break $.each loop
                }
            } else {
                if (m_strain == strain_name && m_sex == sex) {
                    cage.hide = 0;
                    return false; // break $.each loop
                }
            }
        })
    })
}


// modify global_cages insitu
function filter_cages_by_mating(ct) {

    $.each(global_cages, function(cage_id, cage){
        cage.hide = 1;
        $.each(cage.micelist, (i, mk) => {
            m = global_mice[mk];
            if (m.ismating) {
                mousestatus = 'ismating';
            } else {
                mousestatus = 'notmating';
            }

            if (m.comment.indexOf('duesoon') !== -1) {
                mousestatus = 'duesoon';
            }

            if (m.comment.indexOf('lactation') !== -1) {
                mousestatus = 'lactation';
            }

            if (mousestatus == ct) {
                cage.hide = 0;
                return false; // break $.each loop
            }
        })
    })
}


function loadrack() {
    $.ajax({
        type: 'GET',
        url: 'api/allmice.json?t=' + Math.random(),
        success: function(data) {
            global_mice = data.mice;
            global_cages = data.cages;
            global_racks = data.racks;

            let ordered_cage = data.cages;
            Object.keys(ordered_cage).sort((a, b) => {
                return data.cages[a]['col'] > data.cages[b]['col'];
            })
            Object.keys(ordered_cage).sort((a, b) => {
                return data.cages[a]['row'] > data.cages[b]['row'];
            })
            global_cages = ordered_cage;

            $.each(global_cages, function(cage_id, cage){
                cage['hide'] = 0;  // hide cage from rack
            })

            // filter cages on rack
            let racks_html = '';
            $.each(data.racks, function(rackname, rack) {
                racks_html += '<div class="rack"><h2>Rack: ' + rackname + '</h2>';
                racks_html += fmt_rack(rack);
                racks_html += '</div>'

            })
            $('#rack-container').html(racks_html);

            $.each(data.cages, function(cage_id, cage){
                tmp = fmt_cage(cage);
                // 7A, 9F etc.al
                $('#cage-' + cage_id).html(tmp);
            })

            let strains = {};
            $.each(global_mice, (mk, mouse) => {
                let cur_strain = mouse['strain'];
                if (strains[cur_strain] === undefined)
                    strains[cur_strain] = {'f': 0, 'm': 0}
                if (mouse.sex === 'F') {
                    strains[cur_strain]['f'] += 1;
                } else {
                    strains[cur_strain]['m'] += 1;
                }
            })

            /*
            const strains_tbl = Object.keys(strains).map(key =>
                                    [key, strains[key].f, strains[key].m,
                                     strains[key].f + strains[key].m]);
            strains_tbl.unshift(['Strain', 'Female', 'Male', 'Total']);
            strains_tbl.push(total);

            const mice = Object.keys(global_mice).map(key => global_mice[key]);

            console.log(mice);
            const strains = mice.reduce((straincount, m) => {
                let cur_strain = m['strain']
                straincount[cur_strain] = (straincount[cur_strain] || 0) + 1;
                return straincount;
            }, {})
            */
            let strains_tbl = gen_strain_tbl(strains);
			$('#strainscount').html(strains_tbl);
            let cagescount = Object.keys(data.cages).length;
			$('#cagescount').html('<span>Total ' + cagescount + ' cages</span>');
        }
    });
}


function gen_strain_tbl(strains) {
    const strains_rows = Object.keys(strains).map(key =>
                        [key, strains[key].f, strains[key].m,
                         strains[key].f + strains[key].m]);
    strains_rows.sort();
    let tmp = '<table><tr><th>Strain</th><th>Female</th><th>Male</th><th>Total</th></tr>';
    let male_count = 0;
    let female_count = 0;
    let s_array = [];
    $.each(strains_rows, (i, strain) => {
        s_array.push(strain[0]);
        // prepare for filter cage based on strain and/or sex
        tmp += '<tr><td class="clickable-cell strain-filter" data-strain-id="' + i + '">' + strain[0] + '</td>';
        tmp += '<td class="clickable-cell strain-sex-filter" data-sex="F" data-strain-id="' + i + '">' + strain[1] + '</td>';
        tmp += '<td class="clickable-cell strain-sex-filter" data-sex="M" data-strain-id="' + i + '">' + strain[2] + '</td>';
        tmp += '<td>' + strain[3] + '</td></tr>';
        female_count += strain[1];
        male_count += strain[2];
    })

    // global_strains is an array
    global_strains = s_array;

    tmp += '<tr><td></td><td>' + female_count + '</td><td>' + male_count + '</td><td>' + (female_count+male_count) + '</td></tr>'
    ;
    tmp += '</table>';

    return tmp;
}


function firstmouse_in_cage(cage) {{
    firstmouse = cage[0];
    return global_mice[firstmouse];
}}


function fmt_age(age) {
    if (age > 28)
        return Math.floor(age / 7) + 'w';
    else
        return age + 'd';
}

function fmt_cage(cage) {
    /* mouse key: auto increment key in db
     * mouse tag: ear tag
     */
    let cageid = cage.id;
    let cagedesc = cage.desc;
    let rackname = cage.rack;
    let loc = cage.row + cage.col;

    //TODO editable
    let tmp = '<div class="cage-title-container"><span class="cage-title">Rack: ';
    tmp += '<span class="rackname">' + rackname + '</span>' + nbsp;
    tmp += 'Cage: ';
    tmp += '<span class="cageloc">' + loc + '</span>' + nbsp;
    tmp += 'Desc: ';
    tmp += '<span class="cagedesc">' + cagedesc + '</span></span>';


    tmp += '<input class="do-not-print" data-toggle="tooltip" title="Select for Print Cage Card" type="checkbox" name="' + cageid + '"></div>';
    tmp += '<table><tbody>';
    tmp += '<tr><th>Tag</th><th>Sex</th><th>Clr</th><th>Age</th><th>Strain</th><th>Genotyping</th></tr>';

    $.each(cage['micelist'], function(i, mk) {
        m = global_mice[mk];
        if (m.ismating) {
            mousestatus = 'ismating';
        } else {
            mousestatus = 'notmating';
        }

        if (m.comment.indexOf('duesoon') !== -1) {
            mousestatus = 'duesoon';
        }

        if (m.comment.indexOf('lactation') !== -1) {
            mousestatus = 'lactation';
        }

        let cmap = {'Agouti':'AG', 'Black':'BL', 'White':'WH', 'Brown':'BR',
            'GreyWhit': 'GW'};
        tmp += '<tr class="' + mousestatus + ' clickable-cell showmousedetail" data-mouse-key="' + m.mk + '"><td>' + m.tag + '</td>';
        tmp += '<td>' + m.sex + '</td>';
        tmp += '<td>' + cmap[m.color] + '</td>';
        tmp += '<td>' + fmt_age(m.age) + '</td>';
        tmp += '<td>' + m.strain + '</td>';
        tmp += '<td>' + m.genotype.join('</br>') + '</td>';
        tmp += '</tr>';
    })

    tmp += '</tbody></table>';
    return tmp;
}


function short_cagename(longname) {
    /* convert cagename from R1-2M-XXXX to R1-2M */
    let tmp = longname.split("-");
    return tmp[0] + "-" + tmp[1];
}


function fmt_mice_table(mice_keys, mice_details) {
    let tmp = '<table><tbody>';
    tmp += '<tr><th>Tag</th><th>Sex</th><th>Status</th><th>DOB</th><th>Age</th><th>Color</th><th>Origin</th><th>Strain</th><th>Genotype</th><th>Cage</th><th>Comment</th></tr>';
    for (i = 0; i < mice_keys.length; i++) {
        mk = mice_keys[i];
        m = mice_details[mk];
        if (m.lifestatus == 'Alive')
            rowclass = 'alive';
        else
            rowclass = 'not-alive';

        tmp += '<tr class="clickable-cell showmousedetail ' + rowclass + '" data-mouse-key="' + mk + '"><td>' + m.tag + '</td>';
        tmp += '<td>' + m.sex + '</td>';
        tmp += '<td>' + m.lifestatus + '</td>';
        tmp += '<td>' + m.dob + '</td>';
        tmp += '<td>' + fmt_age(m.age) + '</td>';
        tmp += '<td>' + m.color + '</td>';
        tmp += '<td>' + m.origin + '</td>';
        tmp += '<td>' + m.strain + '</td>';
        tmp += '<td>' + m.genotype.join('</br>') + '</td>';
        tmp += '<td>' + short_cagename(m.cagename) + '</td>';
        tmp += '<td>' + m.comment + '</td>';
        tmp += '</tr>';
    }
    tmp += '</tbody></table>';

    return tmp;
}


function fmt_mating(mat) {
    let tmp = '<div class="mating">';
    tmp += '<strong>MatingID: </strong>' + mat.matingid + nbsp;
    tmp += '<strong>Start: </strong>' + mat.matingdate + nbsp;
    tmp += '<strong>End: </strong>' + mat.retiredate + '</br>';

    // use -1 to indicate not dam2
    if (mat.m2 && mat.m2 != -1) {
        partner = [mat.m1, mat.m2];
    } else {
        partner = [mat.m1, ];
    }

    tmp += fmt_mice_table(partner, global_mating_mice)

    if (mat.litters) {
        for (let i=0; i<mat.litters.length; i++) {
            let lt = mat.litters[i];
            tmp += '<div class="litter">';
            tmp += '<strong>LitterID: </strong><span class="clickable-cell ShowLitterDetail" data-litter-key="' + lt.litterkey + '">' + lt.litterid + '</span>' + nbsp;
            tmp += '<strong>Pup Born: </strong>' + lt.litterborn + nbsp;
            tmp += '<strong>DOB: </strong>' + lt.litterdob + '</br>';
            if (lt.littercomment)
                tmp += '<strong>Litter Comment: </strong>' + lt.littercomment + '</br>';
            tmp += '</div>'

        }
    }

    tmp += '</div>';

    return tmp;
}

$(document).on('click', '.ShowLitterDetail', function(event) {
    let lk = $(this).data('litter-key');
    $.ajax({
        type: 'GET',
        url: 'api/litter.json?lk=' + lk + '&t=' + Math.random(),
        success: function(data) {
            let mice= data.mice;

            let tmp = '<div class="push-right-10"><strong>DOB</strong>: ' + data.dob + nbsp;
            tmp += '<strong>WeanDate</strong>: ' + data.wean + nbsp;
            tmp += '<strong>TotalBorn</strong>: ' + data.totalborn + '</br>';
            tmp += '<strong>Comment</strong>: ' + data.comment + '</br>';
            tmp += '</div>';
            tmp += '<h3>Parents</h3>';
            tmp += fmt_mice_table(data.parents, data.mice);
            tmp += '<h3>Siblings</h3>';
            // TODO
            tmp += fmt_mice_table(data.siblings, data.mice);

            $('#mouseDetailTitle').html('<h3>Detail of Litter ' + data.litterID + '</h3>');
            $('#mouseDetail').html(tmp);
            $('#mouseModal').modal('show');
            $(".modal-dialog").draggable({
                    handle: ".modal-header"
            });
        }
    })
})


$(document).on('click', '.showmousedetail', function(event) {
    let mk = $(this).data('mouse-key');
    $.ajax({
        type: 'GET',
        url: 'api/mouse.json?mk=' + mk + '&t=' + Math.random(),
        success: function(data) {
            global_mating_mice = data.mice;
            let m = global_mating_mice[mk];
            let tmp = '<div class="push-right-10"><strong>Sex</strong>: ' + m.sex + nbsp;
            tmp += '<strong>DOB</strong>: ' + m.dob + nbsp;
            tmp += '<strong>Age</strong>: ' + fmt_age(m.age) + nbsp;
            tmp += '<strong>Color</strong>: ' + m.color + nbsp;
            tmp += '<strong>Cage</strong>: ' + m.cagename + nbsp;
            tmp += '<strong>Cageid</strong>: ' + m.cageid + nbsp + '</br>';

            tmp += '<strong>Origin</strong>: ' + m.origin + nbsp;
            if (m.litterkey) {
                tmp += '<strong>LitterID</strong>: <span class="clickable-cell ShowLitterDetail" data-litter-key="' + m.litterkey + '">' + m.litterid + '</span></br>';
            }

            tmp += '<strong>Strain</strong>: ' + m.strain + nbsp;
            tmp += '<strong>Generation</strong>: ' + m.generation + nbsp;
            tmp += '<strong>Genotype</strong>: ' + m.genotype + nbsp + '</br>';
            tmp += '<strong>Comment</strong>: ' + m.comment;
            tmp += '<h3>Mating History</h3>';
            tmp += '</div>';

            $.each(data.mating, function(i, mat) {
                tmp += fmt_mating(mat);
            })

            $('#mouseDetailTitle').html('<h3>Detail of Mouse ' + m.tag + '</h3>');
            $('#mouseDetail').html(tmp);
            $('#mouseModal').modal('show');
            $(".modal-dialog").draggable({
                    handle: ".modal-header"
            });
        }
    })

})


function reset_global_cages() {
    $.each(global_cages, function(cage_id, cage){
        cage['hide'] = 0;  // unhide cage from rack
    })
}


// replot rack, filter by strain
$(document).on('click', '.strain-filter', function(event) {
    let sid = $(this).data('strain-id');
    let t = parseInt(sid) + 100;
    d3.selectAll('.strain-filter').classed('filter-highlight', false);
    d3.selectAll('.strain-sex-filter').classed('filter-highlight', false);
    if (t === global_strain_filter_toggle) {
        global_strain_filter_toggle = -1;
        reset_global_cages();
    } else {
        global_strain_filter_toggle = t;
        let strain_name = global_strains[sid];
        d3.select(this).classed('filter-highlight', true);
        filter_cages_by_strain(strain_name);
    }

    render_rack();
})


// replot rack, filter by strain
$(document).on('click', '.strain-sex-filter', function(event) {
    let sex = $(this).data('sex');
    let sid = $(this).data('strain-id');
    let t;
    if (sex === 'M')
        t = parseInt(sid) + 1000;
    else if (sex === 'F')
        t = parseInt(sid) + 2000;

    d3.selectAll('.strain-filter').classed('filter-highlight', false);
    d3.selectAll('.strain-sex-filter').classed('filter-highlight', false);
    if (t === global_strain_filter_toggle) {
        global_strain_filter_toggle = -1;
        reset_global_cages();
    } else {
        global_strain_filter_toggle = t;
        let strain_name = global_strains[sid];
        d3.select(this).classed('filter-highlight', true);
        filter_cages_by_strain(strain_name, sex);
    }

    render_rack();
})


// replot rack, filter by mating, duesoon, or lactation
$(document).on('click', '.clickable-mdl', function(event) {
    let span_classes = this.classList;
    let mousestatus;

    if ($.inArray('duesoon', span_classes) !== -1) {
        mousestatus = 'duesoon';
    } else if ($.inArray('ismating', span_classes) !== -1) {
        mousestatus = 'ismating';
    } else if ($.inArray('lactation', span_classes) !== -1) {
        mousestatus = 'lactation';
    }

    if (mousestatus == global_mdl_filter_toggle) {
        global_mdl_filter_toggle = undefined;
        reset_global_cages();
    } else {
        filter_cages_by_mating(mousestatus);
        global_mdl_filter_toggle = mousestatus;
    }

    render_rack();
})


function render_rack() {
    /*
    rack_f = {};
    $.each(global_cages, (cid, cage) => {
        if (cage.hide === 1)
            return;  // skip loop

        let r = cage.row;
        if (rack_f[r] === undefined)
            rack_f[r] = [];
        rack_f[r].push(cid);
    })

    // filter cages on rack
    // TODO
    $('#rack-container').html(fmt_rack(rack_f));
    */



    // filter cages on rack
    let racks_html = '';
    $.each(global_racks, function(rackname, rack) {
        let tmp = fmt_rack(rack);
        if (tmp == '')  // empty may indicate all cages are hidden
            return   // skip loop

        racks_html += '<div class="rack"><h2>Rack: ' + rackname + '</h2>';
        racks_html += tmp;
        racks_html += '</div>'

    })
    $('#rack-container').html(racks_html);






    $.each(global_cages, function(cage_id, cage){
        tmp = fmt_cage(cage);
        // 7A, 9F etc.al
        $('#cage-' + cage_id).html(tmp);
    })
}


$(document).on('click', '#print-cagecard', function(event) {
    let cages = [];
    $('input:checkbox').each(function() {
        let cageid =  $(this).attr('name');
        let ischecked = $(this).is(':checked');
        if (ischecked)
            cages.push(cageid);
    })

    if (cages.length === 0) {
        $('#alertDetailTitle').html('<h3>Warning</h3>');
        $('#alertDetail').html('<h4>Please select cages</h4>');
        $('#alertModal').modal('show');
        $(".modal-dialog").draggable({
                handle: ".modal-header"
        });
        return;
    }

 // Use XMLHttpRequest instead of Jquery $ajax
    xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function() {
        var a;
        if (xhttp.readyState === 4 && xhttp.status === 200) {
            // Trick for making downloadable link
            a = document.createElement('a');
            a.href = window.URL.createObjectURL(xhttp.response);
            // Give filename you wish to download
            a.download = "cagecards.pdf";
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
        }
    };
    // Post data to URL which handles post request
    xhttp.open("POST", 'api/print-cagecards');
    xhttp.setRequestHeader("Content-Type", "application/json");
    // You should set responseType as blob for binary responses
    xhttp.responseType = 'blob';
    xhttp.send(JSON.stringify(cages));


})


function makeTable(container, data) {
    var table = $("<table/>").addClass('mytable');
    $.each(data, function(rowIndex, r) {
        var row = $("<tr/>");
        $.each(r, function(colIndex, c) {
            row.append($("<t"+(rowIndex == 0 ?  "h" : "d")+"/>").text(c));
        });
        table.append(row);
    });
    return container.append(table);
}
